"""AI assistant endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..agent.service import DISCLAIMER, AgentService
from ..agent.tools import TOOL_REGISTRY
from ..deps import AppSettings, CurrentUser, DbSession, enforce_ai_rate_limit, record_audit
from ..schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.get("/tools")
def list_tools(settings: AppSettings) -> dict:
    """What the model is allowed to call. Useful for the demo and for review."""
    return {
        "mode": "llm" if settings.llm_enabled else "offline_deterministic",
        "max_tool_iterations": settings.agent_max_tool_iterations,
        "max_tool_calls_per_request": settings.agent_max_tool_calls,
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "mutates_state": spec.mutates_state,
                "parameters": list(spec.args_model.model_fields),
            }
            for spec in TOOL_REGISTRY.values()
        ],
        "notes": [
            "The model has no database access and performs no arithmetic.",
            "Tool arguments are validated server-side; user scope is never a "
            "model-supplied argument.",
            "State-changing results are created as drafts pending user confirmation.",
        ],
    }


@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(enforce_ai_rate_limit)],
)
def chat(
    payload: ChatRequest,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> ChatResponse:
    agent = AgentService(db, user, settings)
    result = agent.run(
        payload.message,
        history=[turn.model_dump() for turn in payload.history],
    )

    record_audit(
        db, user_id=user.id, event="assistant_chat", outcome="ok",
        detail=(
            f"mode={result.mode} iterations={result.iterations} "
            f"tool_calls={len(result.tool_calls)} truncated={result.truncated}"
        ),
    )
    db.commit()

    data = result.to_dict()
    data["disclaimer"] = DISCLAIMER
    return ChatResponse(**data)


@router.get("/suggestions")
def suggestions(user: CurrentUser) -> dict:
    """Starter prompts for the chat empty state — biased toward linked cash-flow questions."""
    return {
        "suggestions": [
            "Can I cover my near-term local bills and still send money home this month?",
            "If I cancel a duplicate subscription, does that free enough for rent or remittance?",
            "Should I hold my next remittance until after local bills clear?",
            "Am I paying for the same subscription twice?",
            "Where do FX fees and foreign-currency spend show up in my cash flow?",
            "What is the single highest-impact saving that protects me from a shortfall?",
        ],
        "base_currency": user.base_currency,
        "persona": user.full_name,
    }
