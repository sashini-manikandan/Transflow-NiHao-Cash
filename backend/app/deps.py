"""Request dependencies: user scoping, rate limiting, audit logging.

The demo identifies a user with the `X-Demo-User` header. This is deliberately
*not* a real authentication scheme — it exists so that every query is scoped to
one user id and the record-isolation rules are actually exercised. A production
deployment would swap `get_current_user` for real session or token auth without
touching any other module.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .models import AuditLog, User

logger = logging.getLogger("billwise.audit")


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_demo_user: Annotated[str | None, Header(alias="X-Demo-User")] = None,
) -> User:
    email = (x_demo_user or settings.demo_user_email).strip().lower()
    if len(email) > 255:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid user identifier.")

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No demo user matches that identifier. Seed the database first.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


class SlidingWindowRateLimiter:
    """Process-local sliding-window limiter.

    Adequate for a single-process MVP. A multi-instance deployment would move
    this to Redis; the interface would not change.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int, float]:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = window_seconds - (now - bucket[0])
            return False, 0, max(retry_after, 1.0)
        bucket.append(now)
        return True, limit - len(bucket), 0.0

    def reset(self) -> None:
        self._hits.clear()


ai_rate_limiter = SlidingWindowRateLimiter()


def enforce_ai_rate_limit(
    request: Request,
    user: CurrentUser,
    settings: AppSettings,
) -> None:
    """Throttle the AI endpoints per user, falling back to client host."""
    client = request.client.host if request.client else "unknown"
    key = f"ai:{user.id}:{client}"
    allowed, remaining, retry_after = ai_rate_limiter.check(
        key, settings.ai_rate_limit_requests, settings.ai_rate_limit_window_seconds
    )
    if not allowed:
        logger.warning("rate_limit_exceeded user_id=%s endpoint=ai", user.id)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many assistant requests. Limit is "
                f"{settings.ai_rate_limit_requests} per "
                f"{settings.ai_rate_limit_window_seconds}s."
            ),
            headers={"Retry-After": str(int(retry_after))},
        )
    request.state.ai_rate_limit_remaining = remaining


def record_audit(
    db: Session,
    *,
    user_id: int | None,
    event: str,
    tool_name: str | None = None,
    authorized: bool | None = None,
    outcome: str = "ok",
    detail: str = "",
) -> None:
    """Append an audit row.

    `detail` is for short, non-sensitive context (tool name, validation error
    kind, counts). Transaction descriptions, balances and message bodies must
    not be passed in.
    """
    entry = AuditLog(
        user_id=user_id,
        event=event,
        tool_name=tool_name,
        authorized=authorized,
        outcome=outcome,
        detail=detail[:512],
    )
    db.add(entry)
    logger.info(
        "audit event=%s tool=%s user_id=%s authorized=%s outcome=%s %s",
        event, tool_name, user_id, authorized, outcome, detail[:200],
    )
