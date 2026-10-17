"""Read-only analysis endpoints: dashboard, subscriptions, bills, currency."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from ..deps import CurrentUser, DbSession, record_audit
from ..models import Bill, FxRate
from ..schemas import BillCreate, BillOut
from ..services.analysis import (
    analyze_currency_costs,
    analyze_subscriptions,
    get_recurring_series,
    get_savings_options,
    get_upcoming_bills,
)
from ..services.dashboard import build_dashboard
from ..services.forecast import forecast_balance
from ..services.merchants import normalize_merchant

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/dashboard")
def dashboard(
    user: CurrentUser,
    db: DbSession,
    horizon_days: int = Query(default=30, ge=7, le=180),
) -> dict:
    return build_dashboard(db, user, horizon_days=horizon_days)


@router.get("/subscriptions")
def subscriptions(
    user: CurrentUser,
    db: DbSession,
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    include_dormant: bool = Query(default=True),
) -> dict:
    return analyze_subscriptions(
        db, user, min_confidence=min_confidence, include_dormant=include_dormant
    )


@router.get("/savings")
def savings(user: CurrentUser, db: DbSession) -> dict:
    options = get_savings_options(db, user)
    return {
        "count": len(options),
        "base_currency": user.base_currency,
        "options": [o.to_dict() for o in options],
    }


@router.get("/bills")
def bills(
    user: CurrentUser,
    db: DbSession,
    days_ahead: int = Query(default=30, ge=1, le=365),
    include_paid: bool = Query(default=False),
) -> dict:
    return get_upcoming_bills(
        db, user, days_ahead=days_ahead, include_paid=include_paid
    )


@router.post("/bills", response_model=BillOut, status_code=status.HTTP_201_CREATED)
def create_bill(payload: BillCreate, user: CurrentUser, db: DbSession) -> BillOut:
    if payload.due_date < date.today() - timedelta(days=365 * 5):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "due_date is implausibly far in the past."
        )
    bill = Bill(
        user_id=user.id,
        name=payload.name,
        merchant_normalized=normalize_merchant(payload.name).key,
        category=payload.category,
        due_date=payload.due_date,
        amount=payload.amount,
        currency=payload.currency,
        status="upcoming",
        is_recurring=payload.is_recurring,
        autopay=payload.autopay,
        source="manual",
        notes=payload.notes,
    )
    db.add(bill)
    record_audit(
        db, user_id=user.id, event="bill_created", outcome="ok",
        detail=f"currency={payload.currency}",
    )
    db.commit()
    db.refresh(bill)
    return BillOut.model_validate(bill)


@router.get("/forecast")
def forecast(
    user: CurrentUser,
    db: DbSession,
    horizon_days: int = Query(default=30, ge=1, le=365),
    include_projected_recurring: bool = Query(default=True),
) -> dict:
    series = get_recurring_series(db, user)
    result = forecast_balance(
        db, user, series,
        horizon_days=horizon_days,
        include_projected_recurring=include_projected_recurring,
    )
    return result.to_dict()


@router.get("/currency")
def currency(
    user: CurrentUser,
    db: DbSession,
    months: int = Query(default=6, ge=1, le=24),
) -> dict:
    return analyze_currency_costs(db, user, months=months)


@router.get("/currency/remittance-sim")
def remittance_sim(
    user: CurrentUser,
    db: DbSession,
    amount: float = Query(..., gt=0, le=1_000_000),
    destination_currency: str = Query(default="GHS", min_length=3, max_length=3),
    source_currency: str | None = Query(default=None, min_length=3, max_length=3),
) -> dict:
    """Sandbox comparison: traditional remittance vs USDC simulation.

    Never executes a transfer. Fees and stablecoin peg are demo estimates.
    """
    from decimal import Decimal

    from ..services.remittance_sim import simulate_remittance

    result = simulate_remittance(
        db,
        user,
        amount=Decimal(str(amount)),
        source_currency=source_currency,
        destination_currency=destination_currency.upper(),
    )
    record_audit(
        db,
        user_id=user.id,
        event="remittance_sim",
        outcome="ok",
        detail=f"dest={destination_currency.upper()} executable=false",
    )
    db.commit()
    return result


@router.get("/currency/rates")
def rates(
    db: DbSession,
    user: CurrentUser,
    quote: str | None = Query(default=None, min_length=3, max_length=3),
    limit: int = Query(default=120, ge=1, le=1000),
) -> dict:
    """Rate history, so the UI can show exactly which numbers were used."""
    stmt = select(FxRate)
    if quote:
        stmt = stmt.where(FxRate.quote_currency == quote.upper())
    rows = (
        db.execute(stmt.order_by(FxRate.as_of_date.desc()).limit(limit)).scalars().all()
    )
    return {
        "base_currency": user.base_currency,
        "count": len(rows),
        "all_rates_simulated": all(r.is_simulated for r in rows),
        "rates": [
            {
                "pair": f"{r.base_currency}/{r.quote_currency}",
                "base_currency": r.base_currency,
                "quote_currency": r.quote_currency,
                "rate": float(r.rate),
                "as_of_date": r.as_of_date.isoformat(),
                "source": r.source,
                "is_simulated": r.is_simulated,
            }
            for r in rows
        ],
    }
