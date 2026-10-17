"""Dashboard aggregation: one call that powers the landing screen."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Transaction, User
from .analysis import (
    analyze_subscriptions,
    get_recurring_series,
    get_savings_options,
    get_upcoming_bills,
)
from .forecast import forecast_balance
from .fx import FxService, q2


def _spend_by_category(
    db: Session, user: User, fx: FxService, today: date, days: int = 30
) -> list[dict]:
    since = today - timedelta(days=days)
    rows = (
        db.execute(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.posted_date >= since,
                Transaction.posted_date <= today,
                Transaction.direction == "debit",
            )
        )
        .scalars()
        .all()
    )
    totals: dict[str, Decimal] = {}
    unconverted = 0
    for row in rows:
        conv = fx.convert(
            row.amount_original, row.currency_original, user.base_currency, row.posted_date
        )
        if not conv.available:
            unconverted += 1
            continue
        totals[row.category] = totals.get(row.category, Decimal("0")) + conv.converted

    result = [
        {"category": name, "amount_base": float(q2(amount))}
        for name, amount in sorted(totals.items(), key=lambda kv: -kv[1])
    ]
    if unconverted:
        result.append(
            {
                "category": "not_converted",
                "amount_base": None,
                "note": f"{unconverted} transaction(s) had no available exchange rate.",
            }
        )
    return result


def build_dashboard(
    db: Session, user: User, today: date | None = None, horizon_days: int = 30
) -> dict:
    today = today or date.today()
    fx = FxService(db)

    series = get_recurring_series(db, user, today=today)
    forecast = forecast_balance(db, user, series, horizon_days=horizon_days, today=today)
    bills = get_upcoming_bills(db, user, days_ahead=horizon_days, today=today)
    subs = analyze_subscriptions(db, user, today=today, series=series)
    savings = get_savings_options(db, user, today=today, series=series)

    savings_total = sum(
        (o.estimated_monthly_saving_base or Decimal("0")) for o in savings
    )

    # Confirmed repricings lead; a shift seen only once is still shown, but
    # after them and flagged as unconfirmed.
    ranked_changes = sorted(
        subs["price_changes"],
        key=lambda c: (not c["confirmed_by_later_charge"], c["effective_date"]),
    )
    price_alerts = [
        {
            "merchant": change["merchant"],
            "previous_amount": change["previous_amount"],
            "new_amount": change["new_amount"],
            "change_amount": change["change_amount"],
            "change_pct": change["change_pct"],
            "currency": change["currency"],
            "effective_date": change["effective_date"],
            "direction": change["direction"],
            "confidence": change["confidence"],
            "confirmed_by_later_charge": change["confirmed_by_later_charge"],
        }
        for change in ranked_changes[:6]
    ]

    return {
        "as_of": today.isoformat(),
        "user": {
            "name": user.full_name,
            "base_currency": user.base_currency,
            "home_country": user.home_country,
            "study_country": user.study_country,
            "priorities": user.priority_list,
        },
        "data_source": {
            "is_demo_data": True,
            "label": "Synthetic demo data — no bank account is connected.",
        },
        "available_balance": {
            "amount": float(forecast.opening_balance),
            "currency": user.base_currency,
            "basis": "calculated",
            "accounts": forecast.opening_balance_breakdown,
            "excluded": [
                item for item in forecast.excluded if item["item"].startswith("Opening balance")
            ],
        },
        "upcoming_bills": {
            "count": bills["count"],
            "total_base": bills["total_due_base"],
            "currency": user.base_currency,
            "window_days": horizon_days,
            "basis": "calculated",
            "next": bills["bills"][:5],
        },
        "recurring_monthly": {
            "amount": subs["summary"]["estimated_monthly_total_base"],
            "currency": user.base_currency,
            "active_count": subs["summary"]["active_count"],
            "likely_count": subs["summary"]["likely_count"],
            "possible_count": subs["summary"]["possible_count"],
            "basis": "estimate",
            "note": (
                "Normalised to a monthly figure from each detected cadence. "
                "Includes possible as well as likely recurring charges."
            ),
        },
        "potential_savings": {
            "amount": float(q2(Decimal(savings_total))),
            "currency": user.base_currency,
            "option_count": len(savings),
            "basis": "estimate",
            "note": (
                "Upper bound if every suggestion below is acted on. Each option "
                "lists its own confidence and conditions."
            ),
        },
        "price_change_alerts": price_alerts,
        "cash_flow": {
            "currency": user.base_currency,
            "horizon_days": horizon_days,
            "period": {
                "start": forecast.start_date.isoformat(),
                "end": forecast.end_date.isoformat(),
                "horizon_days": horizon_days,
            },
            "opening_balance": float(forecast.opening_balance),
            "closing_balance": float(forecast.closing_balance),
            "minimum_balance": float(forecast.minimum_balance),
            "minimum_balance_date": forecast.minimum_balance_date.isoformat(),
            "shortfall_detected": forecast.shortfall_detected,
            "first_shortfall_date": forecast.first_shortfall_date.isoformat()
            if forecast.first_shortfall_date
            else None,
            "largest_shortfall": float(forecast.largest_shortfall)
            if forecast.largest_shortfall is not None
            else None,
            "total_inflow": float(forecast.total_inflow),
            "total_outflow": float(forecast.total_outflow),
            "series": forecast.daily,
            "assumptions": forecast.assumptions,
            "excluded_from_projection": forecast.excluded,
            "basis": "estimate",
        },
        "spend_by_category_30d": _spend_by_category(db, user, fx, today),
        "duplicate_findings_count": subs["summary"]["duplicate_findings"],
    }
