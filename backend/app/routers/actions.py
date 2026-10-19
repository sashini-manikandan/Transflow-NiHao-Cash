"""Recommendations, reminders, and the authorization flow for actions.

Nothing in this module performs a real-world action. A cancellation produces a
preview the user must explicitly approve, and approval marks it ready to action
manually — it never contacts a merchant.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from ..deps import CurrentUser, DbSession, record_audit
from ..models import ActionPreview, Reminder
from ..schemas import (
    ActionDecision,
    ActionPreviewCreate,
    ActionPreviewOut,
    ReminderCreate,
    ReminderOut,
)
from ..services.analysis import get_recurring_series
from ..services.fx import FxService
from ..services.recommendations import build_recommendations

router = APIRouter(prefix="/api", tags=["actions"])


@router.get("/recommendations")
def recommendations(
    user: CurrentUser,
    db: DbSession,
    horizon_days: int = Query(default=30, ge=7, le=180),
    limit: int = Query(default=10, ge=1, le=25),
) -> dict:
    items = build_recommendations(db, user, horizon_days=horizon_days, limit=limit)
    return {
        "count": len(items),
        "base_currency": user.base_currency,
        "ranking": {
            "weights": {
                "urgency": 0.34,
                "estimated_impact": 0.30,
                "confidence": 0.22,
                "stated_priorities": 0.14,
            },
            "user_priorities": user.priority_list,
        },
        "recommendations": [i.to_dict() for i in items],
    }


# --------------------------------------------------------------------------
# reminders
# --------------------------------------------------------------------------
@router.get("/reminders", response_model=list[ReminderOut])
def list_reminders(user: CurrentUser, db: DbSession) -> list[ReminderOut]:
    rows = (
        db.execute(
            select(Reminder)
            .where(Reminder.user_id == user.id)
            .order_by(Reminder.due_date)
        )
        .scalars()
        .all()
    )
    return [ReminderOut.model_validate(r) for r in rows]


@router.post("/reminders", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
def create_reminder(
    payload: ReminderCreate, user: CurrentUser, db: DbSession
) -> ReminderOut:
    reminder = Reminder(
        user_id=user.id,
        title=payload.title,
        due_date=payload.due_date,
        note=payload.note,
        related_kind=payload.related_kind,
        related_ref=payload.related_ref,
        created_by="user",
        status="active",
    )
    db.add(reminder)
    record_audit(
        db, user_id=user.id, event="reminder_created", authorized=True, outcome="ok",
        detail="created_by=user",
    )
    db.commit()
    db.refresh(reminder)
    return ReminderOut.model_validate(reminder)


@router.post("/reminders/{reminder_id}/confirm", response_model=ReminderOut)
def confirm_reminder(
    reminder_id: int, user: CurrentUser, db: DbSession
) -> ReminderOut:
    """Activate a reminder the assistant drafted. This is the authorization step."""
    reminder = db.execute(
        select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user.id)
    ).scalar_one_or_none()
    if reminder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reminder not found.")
    if reminder.status != "pending_confirmation":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Reminder is '{reminder.status}' and does not need confirmation.",
        )

    reminder.status = "active"
    record_audit(
        db, user_id=user.id, event="reminder_confirmed", authorized=True, outcome="ok",
        detail=f"reminder_id={reminder.id} created_by={reminder.created_by}",
    )
    db.commit()
    db.refresh(reminder)
    return ReminderOut.model_validate(reminder)


@router.delete(
    "/reminders/{reminder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def dismiss_reminder(reminder_id: int, user: CurrentUser, db: DbSession) -> None:
    reminder = db.execute(
        select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user.id)
    ).scalar_one_or_none()
    if reminder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reminder not found.")
    reminder.status = "dismissed"
    record_audit(
        db, user_id=user.id, event="reminder_dismissed", authorized=True, outcome="ok",
        detail=f"reminder_id={reminder.id}",
    )
    db.commit()


# --------------------------------------------------------------------------
# action previews
# --------------------------------------------------------------------------
@router.get("/actions", response_model=list[ActionPreviewOut])
def list_actions(user: CurrentUser, db: DbSession) -> list[ActionPreviewOut]:
    rows = (
        db.execute(
            select(ActionPreview)
            .where(ActionPreview.user_id == user.id)
            .order_by(ActionPreview.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [ActionPreviewOut.model_validate(r) for r in rows]


@router.post(
    "/actions/preview",
    response_model=ActionPreviewOut,
    status_code=status.HTTP_201_CREATED,
)
def preview_action(
    payload: ActionPreviewCreate, user: CurrentUser, db: DbSession
) -> ActionPreviewOut:
    """Build a reviewable preview. This never cancels anything."""
    today = date.today()
    series = get_recurring_series(db, user, today=today)
    matches = [s for s in series if s.merchant.lower() == payload.target_label.lower()]

    if not matches:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No detected recurring payment matches '{payload.target_label}'.",
        )

    fx = FxService(db)
    impact: Decimal | None = None
    lines: list[str] = []
    for match in matches:
        conv = fx.convert(match.monthly_equivalent, match.currency, user.base_currency, today)
        if conv.available:
            impact = (impact or Decimal("0")) + conv.converted
        lines.append(
            f"{match.merchant}: {match.currency} {match.latest_amount:.2f} "
            f"{match.cadence}, last charged {match.last_seen.isoformat()}, "
            f"{len(match.occurrences)} charges observed "
            f"(detection confidence {match.confidence:.2f})."
        )

    summary = (
        f"Preview only — nothing has been cancelled.\n"
        + "\n".join(lines)
        + "\n\nIf you approve this, Tran$Flow records your decision and shows you "
        "the steps to cancel with the merchant. Tran$Flow cannot contact the "
        "merchant or stop a payment on your behalf."
    )

    preview = ActionPreview(
        user_id=user.id,
        action_type=payload.action_type,
        target_label=payload.target_label,
        summary=summary,
        estimated_monthly_impact=impact,
        currency=user.base_currency if impact is not None else None,
        status="pending_review",
        requires_authorization=True,
    )
    db.add(preview)
    record_audit(
        db, user_id=user.id, event="action_preview_created", authorized=False,
        outcome="pending_review",
        detail=f"action_type={payload.action_type} matches={len(matches)}",
    )
    db.commit()
    db.refresh(preview)
    return ActionPreviewOut.model_validate(preview)


@router.post("/actions/{action_id}/decision", response_model=ActionPreviewOut)
def decide_action(
    action_id: int, payload: ActionDecision, user: CurrentUser, db: DbSession
) -> ActionPreviewOut:
    """Record the user's explicit decision on a previewed action."""
    preview = db.execute(
        select(ActionPreview).where(
            ActionPreview.id == action_id, ActionPreview.user_id == user.id
        )
    ).scalar_one_or_none()
    if preview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action preview not found.")
    if preview.status != "pending_review":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This action is already '{preview.status}'.",
        )

    if payload.decision == "approve":
        expected = preview.target_label.strip().lower()
        if payload.confirmation_text.strip().lower() != expected:
            record_audit(
                db, user_id=user.id, event="action_authorization",
                authorized=False, outcome="confirmation_mismatch",
                detail=f"action_id={preview.id}",
            )
            db.commit()
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"To approve, type the exact name '{preview.target_label}' to confirm.",
            )
        preview.status = "approved_by_user"
        outcome = "approved"
    else:
        preview.status = "declined_by_user"
        outcome = "declined"

    record_audit(
        db, user_id=user.id, event="action_authorization",
        authorized=payload.decision == "approve", outcome=outcome,
        detail=f"action_id={preview.id} action_type={preview.action_type}",
    )
    db.commit()
    db.refresh(preview)
    return ActionPreviewOut.model_validate(preview)
