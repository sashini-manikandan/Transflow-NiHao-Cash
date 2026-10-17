"""Balance projection over a horizon.

Combines three streams of expected money movement:
  1. confirmed bills with a due date,
  2. projected charges from detected recurring series,
  3. expected income from configured inflows.

Anything that cannot be converted into the reporting currency is *excluded
from the running balance* and listed separately with the reason, rather than
being silently dropped or estimated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, Bill, IncomeSource, User
from .fx import FxService, q2
from .recurring import RecurringSeries, project_next_date

# A projected recurring charge is suppressed when a real bill for the same
# merchant already sits within this many days of it.
BILL_DEDUPE_WINDOW_DAYS = 6


@dataclass
class ForecastEvent:
    event_date: date
    label: str
    kind: str                 # bill | recurring_charge | income
    direction: str            # inflow | outflow
    amount_original: Decimal
    currency_original: str
    amount_base: Decimal | None
    conversion_status: str
    certainty: str            # confirmed | projected | estimated
    confidence: float
    source_note: str = ""
    fx_note: str = ""
    # Same caveat as fx_note, in a form a caller can act on without parsing prose.
    rate_stale: bool = False

    def to_dict(self) -> dict:
        return {
            "date": self.event_date.isoformat(),
            "label": self.label,
            "kind": self.kind,
            "direction": self.direction,
            "amount_original": float(self.amount_original),
            "currency_original": self.currency_original,
            "amount_base": float(self.amount_base) if self.amount_base is not None else None,
            "conversion_status": self.conversion_status,
            "certainty": self.certainty,
            "confidence": round(self.confidence, 2),
            "rate_stale": self.rate_stale,
            "source_note": self.source_note,
            "fx_note": self.fx_note,
        }


@dataclass
class ForecastResult:
    base_currency: str
    start_date: date
    end_date: date
    horizon_days: int
    opening_balance: Decimal
    closing_balance: Decimal
    total_inflow: Decimal
    total_outflow: Decimal
    minimum_balance: Decimal
    minimum_balance_date: date
    shortfall_detected: bool
    first_shortfall_date: date | None
    largest_shortfall: Decimal | None
    daily: list[dict] = field(default_factory=list)
    events: list[ForecastEvent] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    opening_balance_breakdown: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "base_currency": self.base_currency,
            "period": {
                "start": self.start_date.isoformat(),
                "end": self.end_date.isoformat(),
                "horizon_days": self.horizon_days,
            },
            "opening_balance": float(self.opening_balance),
            "closing_balance": float(self.closing_balance),
            "total_inflow": float(self.total_inflow),
            "total_outflow": float(self.total_outflow),
            "net_change": float(self.closing_balance - self.opening_balance),
            "minimum_balance": float(self.minimum_balance),
            "minimum_balance_date": self.minimum_balance_date.isoformat(),
            "shortfall_detected": self.shortfall_detected,
            "first_shortfall_date": self.first_shortfall_date.isoformat()
            if self.first_shortfall_date
            else None,
            "largest_shortfall": float(self.largest_shortfall)
            if self.largest_shortfall is not None
            else None,
            "daily": self.daily,
            "events": [e.to_dict() for e in self.events],
            "excluded_from_projection": self.excluded,
            "assumptions": self.assumptions,
            "opening_balance_breakdown": self.opening_balance_breakdown,
        }


def _opening_balance(
    db: Session, user: User, fx: FxService, today: date
) -> tuple[Decimal, list[dict], list[dict]]:
    accounts = db.execute(select(Account).where(Account.user_id == user.id)).scalars().all()
    total = Decimal("0")
    breakdown: list[dict] = []
    excluded: list[dict] = []

    for account in accounts:
        conv = fx.convert(account.current_balance, account.currency, user.base_currency, today)
        entry = {
            "account_id": account.id,
            "name": account.name,
            "institution": account.institution,
            "currency": account.currency,
            "balance_original": float(account.current_balance),
            "balance_base": float(conv.converted) if conv.available else None,
            "conversion": conv.to_dict(),
        }
        breakdown.append(entry)
        if conv.available:
            total += conv.converted
        else:
            excluded.append(
                {
                    "item": f"Opening balance of {account.name}",
                    "amount_original": float(account.current_balance),
                    "currency": account.currency,
                    "reason": conv.note,
                }
            )
    return q2(total), breakdown, excluded


def _project_series_dates(
    series: RecurringSeries, start: date, end: date
) -> list[date]:
    """Expected charge dates for a series inside [start, end]."""
    if series.status != "active" or series.next_expected_date is None:
        return []
    dates: list[date] = []
    cursor = series.next_expected_date
    guard = 0
    while cursor <= end and guard < 64:
        if cursor >= start:
            dates.append(cursor)
        cursor = project_next_date(cursor, series.cadence, series.median_interval_days)
        guard += 1
    return dates


def _project_income_dates(source: IncomeSource, start: date, end: date) -> list[date]:
    step_months = {"monthly": 1, "bimonthly": 2, "quarterly": 3, "semiannual": 6, "annual": 12}
    months = step_months.get(source.cadence, 1)
    dates: list[date] = []
    cursor = source.next_expected_date
    guard = 0
    while cursor <= end and guard < 64:
        if cursor >= start:
            dates.append(cursor)
        cursor = project_next_date(cursor, _cadence_name(months), months * 30)
        guard += 1
    return dates


def _cadence_name(months: int) -> str:
    return {1: "monthly", 2: "bimonthly", 3: "quarterly", 6: "semiannual", 12: "annual"}.get(
        months, "monthly"
    )


_INCOME_CONFIDENCE = {"high": 0.9, "medium": 0.7, "low": 0.45}


def forecast_balance(
    db: Session,
    user: User,
    series_list: list[RecurringSeries],
    horizon_days: int = 30,
    today: date | None = None,
    include_projected_recurring: bool = True,
) -> ForecastResult:
    today = today or date.today()
    horizon_days = max(1, min(horizon_days, 365))
    end_date = today + timedelta(days=horizon_days)
    fx = FxService(db)

    opening, breakdown, excluded = _opening_balance(db, user, fx, today)
    events: list[ForecastEvent] = []
    assumptions: list[str] = [
        "Opening balance is the sum of demo account balances converted at the "
        "most recent stored rate on or before today.",
        "All figures use clearly-labelled synthetic demo data and simulated FX rates.",
    ]

    # --- confirmed bills ---------------------------------------------------
    bills = (
        db.execute(
            select(Bill).where(
                Bill.user_id == user.id,
                Bill.status != "paid",
                Bill.due_date >= today,
                Bill.due_date <= end_date,
            )
        )
        .scalars()
        .all()
    )
    billed_merchants: list[tuple[str, date]] = []
    for bill in bills:
        conv = fx.convert(bill.amount, bill.currency, user.base_currency, bill.due_date)
        billed_merchants.append((bill.merchant_normalized or bill.name, bill.due_date))
        if not conv.available:
            excluded.append(
                {
                    "item": bill.name,
                    "amount_original": float(bill.amount),
                    "currency": bill.currency,
                    "due_date": bill.due_date.isoformat(),
                    "reason": conv.note,
                }
            )
        events.append(
            ForecastEvent(
                event_date=bill.due_date,
                label=bill.name,
                kind="bill",
                direction="outflow",
                amount_original=bill.amount,
                currency_original=bill.currency,
                amount_base=conv.converted,
                conversion_status=conv.status,
                certainty="confirmed",
                confidence=0.98 if bill.autopay else 0.95,
                source_note="Scheduled bill with a known due date.",
                fx_note=conv.note,
                rate_stale=conv.is_stale,
            )
        )

    # --- projected recurring charges --------------------------------------
    if include_projected_recurring:
        assumptions.append(
            "Projected subscription charges assume each detected series "
            "continues at its most recent amount and observed cadence."
        )
        for series in series_list:
            if series.verdict not in {"likely_recurring", "possible_recurring"}:
                continue
            for charge_date in _project_series_dates(series, today, end_date):
                if any(
                    merchant == series.merchant
                    and abs((charge_date - due).days) <= BILL_DEDUPE_WINDOW_DAYS
                    for merchant, due in billed_merchants
                ):
                    continue
                conv = fx.convert(
                    series.latest_amount, series.currency, user.base_currency, charge_date
                )
                if not conv.available:
                    excluded.append(
                        {
                            "item": f"{series.merchant} (projected charge)",
                            "amount_original": float(series.latest_amount),
                            "currency": series.currency,
                            "due_date": charge_date.isoformat(),
                            "reason": conv.note,
                        }
                    )
                events.append(
                    ForecastEvent(
                        event_date=charge_date,
                        label=f"{series.merchant} ({series.cadence})",
                        kind="recurring_charge",
                        direction="outflow",
                        amount_original=series.latest_amount,
                        currency_original=series.currency,
                        amount_base=conv.converted,
                        conversion_status=conv.status,
                        certainty="projected",
                        confidence=series.confidence,
                        source_note=(
                            f"Projected from {len(series.occurrences)} observed charges "
                            f"({series.verdict.replace('_', ' ')})."
                        ),
                        fx_note=conv.note,
                        rate_stale=conv.is_stale,
                    )
                )

    # --- expected income ---------------------------------------------------
    income_sources = (
        db.execute(select(IncomeSource).where(IncomeSource.user_id == user.id)).scalars().all()
    )
    for source in income_sources:
        for pay_date in _project_income_dates(source, today, end_date):
            conv = fx.convert(source.amount, source.currency, user.base_currency, pay_date)
            if not conv.available:
                excluded.append(
                    {
                        "item": f"{source.name} (expected inflow)",
                        "amount_original": float(source.amount),
                        "currency": source.currency,
                        "due_date": pay_date.isoformat(),
                        "reason": conv.note,
                    }
                )
            events.append(
                ForecastEvent(
                    event_date=pay_date,
                    label=source.name,
                    kind="income",
                    direction="inflow",
                    amount_original=source.amount,
                    currency_original=source.currency,
                    amount_base=conv.converted,
                    conversion_status=conv.status,
                    certainty="projected" if source.confidence != "high" else "confirmed",
                    confidence=_INCOME_CONFIDENCE.get(source.confidence, 0.6),
                    source_note=source.notes or f"{source.cadence} inflow.",
                    fx_note=conv.note,
                    rate_stale=conv.is_stale,
                )
            )

    events.sort(key=lambda e: (e.event_date, e.direction))

    # --- walk the horizon day by day --------------------------------------
    by_day: dict[date, list[ForecastEvent]] = {}
    for event in events:
        by_day.setdefault(event.event_date, []).append(event)

    balance = opening
    total_in = Decimal("0")
    total_out = Decimal("0")
    daily: list[dict] = []
    min_balance = opening
    min_date = today
    first_shortfall: date | None = None
    largest_shortfall: Decimal | None = None

    for offset in range(horizon_days + 1):
        day = today + timedelta(days=offset)
        day_in = Decimal("0")
        day_out = Decimal("0")
        for event in by_day.get(day, []):
            if event.amount_base is None:
                continue  # excluded, already reported
            if event.direction == "inflow":
                day_in += event.amount_base
            else:
                day_out += event.amount_base
        balance = balance + day_in - day_out
        total_in += day_in
        total_out += day_out

        if balance < min_balance:
            min_balance, min_date = balance, day
        if balance < 0:
            if first_shortfall is None:
                first_shortfall = day
            shortfall = -balance
            if largest_shortfall is None or shortfall > largest_shortfall:
                largest_shortfall = shortfall

        daily.append(
            {
                "date": day.isoformat(),
                "balance": float(q2(balance)),
                "inflow": float(q2(day_in)),
                "outflow": float(q2(day_out)),
                "events": [e.label for e in by_day.get(day, [])],
            }
        )

    if excluded:
        assumptions.append(
            f"{len(excluded)} item(s) could not be converted to {user.base_currency} "
            "and are listed separately instead of being estimated."
        )

    return ForecastResult(
        base_currency=user.base_currency,
        start_date=today,
        end_date=end_date,
        horizon_days=horizon_days,
        opening_balance=opening,
        closing_balance=q2(balance),
        total_inflow=q2(total_in),
        total_outflow=q2(total_out),
        minimum_balance=q2(min_balance),
        minimum_balance_date=min_date,
        shortfall_detected=first_shortfall is not None,
        first_shortfall_date=first_shortfall,
        largest_shortfall=q2(largest_shortfall) if largest_shortfall is not None else None,
        daily=daily,
        events=events,
        excluded=excluded,
        assumptions=assumptions,
        opening_balance_breakdown=breakdown,
    )
