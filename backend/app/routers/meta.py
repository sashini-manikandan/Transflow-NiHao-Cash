"""Health, profile and demo-reset endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings
from ..deps import AppSettings, CurrentUser, DbSession
from ..schemas import AccountOut, UserProfileOut

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health(settings: AppSettings) -> dict:
    """Liveness plus the capability flags the frontend needs.

    Deliberately reports only *whether* a key is configured, never its value.
    """
    provider = None
    model = None
    if settings.llm_enabled:
        provider = "openrouter" if settings.is_openrouter else "openai"
        model = settings.openai_model
        if settings.is_openrouter and "/" not in model:
            model = f"openai/{model}"
    return {
        "status": "ok",
        "environment": settings.app_env,
        "assistant_mode": "llm" if settings.llm_enabled else "offline_deterministic",
        "provider": provider,
        "model": model,
        "demo_data": True,
    }


@router.get("/personas")
def personas() -> dict:
    """Demo student personas available via the X-Demo-User header."""
    from ..seed.seed_data import list_demo_personas

    return {
        "personas": list_demo_personas(),
        "note": (
            "Switch personas with the X-Demo-User header (or the sidebar control). "
            "This is demo scoping, not authentication."
        ),
    }


@router.get("/me", response_model=UserProfileOut)
def me(user: CurrentUser, db: DbSession) -> UserProfileOut:
    from sqlalchemy import select

    from ..models import Account

    accounts = (
        db.execute(select(Account).where(Account.user_id == user.id)).scalars().all()
    )
    return UserProfileOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        base_currency=user.base_currency,
        home_country=user.home_country,
        study_country=user.study_country,
        priorities=user.priority_list,
        accounts=[AccountOut.model_validate(a) for a in accounts],
    )
