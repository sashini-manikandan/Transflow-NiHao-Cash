"""Orchestration layer: turns stored rows into analysed, reporting-currency
results. Routers and the AI agent's tools both call into here, so the numbers
the user sees and the numbers the model reasons over are produced by the same
code path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Bill, Transaction, User
from .duplicates import DuplicateFinding, analyze_duplicates
from .fx import FxService, q2
from .merchants import normalize_merchant
from .recurring import (
    RecurringSeries,
    TxnRecord,
    detect_recurring,
    reportable_price_changes,
)

DEFAULT_LOOKBACK_DAYS = 420


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------
def load_txn_records(
    db: Session,
    user_id: int,
    since: date | None = None,
    until: date | None = None,
) -> list[TxnRecord]:
    """Fetch a user's transactions as detector-friendly records.

    Always filtered by user_id: no query in this module can reach another
    user's rows.
    """
    stmt = select(Transaction).where(Transaction.user_id == user_id)
    if since is not None:
        stmt = stmt.where(Transaction.posted_date >= since)
    if until is not None:
        stmt = stmt.where(Transaction.posted_date <= until)
    rows = db.execute(stmt.order_by(Transaction.posted_date)).scalars().all()

    records: list[TxnRecord] = []
    for row in rows:
        merchant = row.merchant_normalized or normalize_merchant(row.description_raw).key
        records.append(
            TxnRecord(
                id=row.id,
                posted_date=row.posted_date,
                amount=Decimal(row.amount_original),
                currency=row.currency_original,
                merchant=merchant,
                account_id=row.account_id,
                description=row.description_raw,
                family=normalize_merchant(row.description_raw).family,
                direction=row.direction,
            )
        )
    return records


def get_recurring_series(
    db: Session,
    user: User,
    today: date | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[RecurringSeries]:
    today = today or date.today()
    records = load_txn_records(db, user.id, since=today - timedelta(days=lookback_days))
    return detect_recurring(records, today=today)


# --------------------------------------------------------------------------
# subscriptions
# --------------------------------------------------------------------------
def _series_with_base(
    series: RecurringSeries, fx: FxService, base_currency: str, today: date
) -> dict:
    payload = series.to_dict()
    payload["price_changes"] = [c.to_dict() for c in reportable_price_changes(series)]
    monthly = fx.convert(series.monthly_equivalent, series.currency, base_currency, today)
    latest = fx.convert(series.latest_amount, series.currency, base_currency, today)
    payload["monthly_equivalent_base"] = (
        float(monthly.converted) if monthly.available else None
    )
    payload["latest_amount_base"] = float(latest.converted) if latest.available else None
    payload["base_currency"] = base_currency
    payload["conversion"] = monthly.to_dict()
    return payload


def analyze_subscriptions(
    db: Session,
    user: User,
    today: date | None = None,
    min_confidence: float = 0.0,
    include_dormant: bool = True,
    series: list[RecurringSeries] | None = None,
) -> dict:
    """Pass `series` when the caller has already run detection for this date;
    recurrence detection is the expensive step and re-running it is pure waste.
    """
    today = today or date.today()
    fx = FxService(db)
    series_list = series if series is not None else get_recurring_series(db, user, today=today)

    visible = [
        s
        for s in series_list
        if s.confidence >= min_confidence and (include_dormant or s.status == "active")
    ]

    findings: list[DuplicateFinding] = analyze_duplicates(series_list)

    price_changes: list[dict] = []
    for series in series_list:
        for change in reportable_price_changes(series):
            entry = change.to_dict()
            conv = fx.convert(
                change.change_amount, change.currency, user.base_currency, change.effective_date
            )
            entry["change_amount_base"] = float(conv.converted) if conv.available else None
            entry["base_currency"] = user.base_currency
            entry["cadence"] = series.cadence
            entry["series_confidence"] = round(series.confidence, 2)
            price_changes.append(entry)
    price_changes.sort(key=lambda c: c["effective_date"], reverse=True)

    active = [s for s in series_list if s.status == "active"]
    monthly_total = Decimal("0")
    unconverted: list[dict] = []
    for series in active:
        if series.verdict == "insufficient_evidence":
            continue
        conv = fx.convert(series.monthly_equivalent, series.currency, user.base_currency, today)
        if conv.available:
            monthly_total += conv.converted
        else:
            unconverted.append(
                {
                    "merchant": series.merchant,
                    "amount": float(series.monthly_equivalent),
                    "currency": series.currency,
                    "reason": conv.note,
                }
            )

    counted = [s for s in active if s.verdict != "insufficient_evidence"]
    return {
        "as_of": today.isoformat(),
        "base_currency": user.base_currency,
        "summary": {
            "series_detected": len(series_list),
            "active_count": len(counted),
            "likely_count": sum(1 for s in counted if s.verdict == "likely_recurring"),
            "possible_count": sum(1 for s in counted if s.verdict == "possible_recurring"),
            "dormant_count": sum(1 for s in series_list if s.status == "dormant"),
            "estimated_monthly_total_base": float(q2(monthly_total)),
            "estimated_annual_total_base": float(q2(monthly_total * 12)),
            "amounts_excluded_for_missing_rates": unconverted,
            "duplicate_findings": len(findings),
            "price_changes_detected": len(price_changes),
        },
        "subscriptions": [
            _series_with_base(s, fx, user.base_currency, today) for s in visible
        ],
        "duplicate_findings": [f.to_dict() for f in findings],
        "price_changes": price_changes,
        "methodology": (
            "Charges are grouped by normalised merchant, currency and account. "
            "Confidence blends spacing regularity, amount stability, how many "
            "charges were observed, and whether the spacing matches a standard "
            "billing cycle. Anything below the 'possible' threshold is reported "
            "as insufficient evidence rather than as a subscription."
        ),
        "data_disclaimer": "All figures come from synthetic demo data.",
    }


# --------------------------------------------------------------------------
# cross-border
# --------------------------------------------------------------------------
def analyze_currency_costs(
    db: Session, user: User, months: int = 6, today: date | None = None
) -> dict:
    today = today or date.today()
    months = max(1, min(months, 24))
    since = today - timedelta(days=months * 30)
    fx = FxService(db)

    rows = (
        db.execute(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.posted_date >= since,
                Transaction.posted_date <= today,
            )
        )
        .scalars()
        .all()
    )

    per_currency: dict[str, dict] = {}
    unconvertible: list[dict] = []
    total_foreign_base = Decimal("0")
    total_fees_base = Decimal("0")
    fees_disclosed = 0

    for row in rows:
        if row.direction != "debit":
            continue
        currency = row.currency_original
        bucket = per_currency.setdefault(
            currency,
            {
                "currency": currency,
                "transaction_count": 0,
                "total_original": Decimal("0"),
                "total_base": Decimal("0"),
                "disclosed_fees_original": Decimal("0"),
                "disclosed_fees_base": Decimal("0"),
                "converted_count": 0,
                "unconverted_count": 0,
                "latest_rate": None,
                "rate_date": None,
                "rate_source": None,
                "is_simulated_rate": None,
            },
        )
        bucket["transaction_count"] += 1
        bucket["total_original"] += Decimal(row.amount_original)

        conv = fx.convert(
            row.amount_original, currency, user.base_currency, row.posted_date
        )
        if conv.available:
            bucket["total_base"] += conv.converted
            bucket["converted_count"] += 1
            bucket["latest_rate"] = float(conv.rate) if conv.rate is not None else None
            bucket["rate_date"] = conv.rate_date.isoformat() if conv.rate_date else None
            bucket["rate_source"] = conv.rate_source
            bucket["is_simulated_rate"] = conv.is_simulated
            if currency != user.base_currency:
                total_foreign_base += conv.converted
        else:
            bucket["unconverted_count"] += 1
            unconvertible.append(
                {
                    "transaction_id": row.id,
                    "date": row.posted_date.isoformat(),
                    "merchant": row.merchant_normalized,
                    "amount": float(row.amount_original),
                    "currency": currency,
                    "reason": conv.note,
                }
            )

        if row.fee_amount is not None and row.fee_currency:
            fees_disclosed += 1
            bucket["disclosed_fees_original"] += Decimal(row.fee_amount)
            fee_conv = fx.convert(
                row.fee_amount, row.fee_currency, user.base_currency, row.posted_date
            )
            if fee_conv.available:
                bucket["disclosed_fees_base"] += fee_conv.converted
                total_fees_base += fee_conv.converted

    breakdown = []
    for bucket in per_currency.values():
        breakdown.append(
            {
                **bucket,
                "total_original": float(q2(bucket["total_original"])),
                "total_base": float(q2(bucket["total_base"])),
                "disclosed_fees_original": float(q2(bucket["disclosed_fees_original"])),
                "disclosed_fees_base": float(q2(bucket["disclosed_fees_base"])),
                "is_base_currency": bucket["currency"] == user.base_currency,
            }
        )
    breakdown.sort(key=lambda b: -b["total_base"])

    # Sensitivity is explicitly a what-if, not a prediction.
    sensitivity = [
        {
            "scenario": f"{pct:+d}% move against {user.base_currency}",
            "monthly_impact_base": float(
                q2(total_foreign_base / Decimal(months) * Decimal(pct) / Decimal(100))
            ),
        }
        for pct in (-10, -5, 5, 10)
    ]

    months_dec = Decimal(months)
    return {
        "as_of": today.isoformat(),
        "base_currency": user.base_currency,
        "period": {
            "start": since.isoformat(),
            "end": today.isoformat(),
            "months": months,
        },
        "summary": {
            "currencies_used": len(per_currency),
            "foreign_currency_spend_base": float(q2(total_foreign_base)),
            "foreign_spend_monthly_average_base": float(q2(total_foreign_base / months_dec)),
            "disclosed_fees_base": float(q2(total_fees_base)),
            "disclosed_fee_transaction_count": fees_disclosed,
            "unconvertible_transaction_count": len(unconvertible),
        },
        "by_currency": breakdown,
        "fx_sensitivity_whatif": sensitivity,
        "unconvertible_transactions": unconvertible,
        "notes": [
            "Only fees the statement actually discloses are counted. Spreads "
            "baked into a provider's rate are not visible in this data and are "
            "not estimated here.",
            "Exchange rates are simulated demo data with the rate date shown "
            "for each conversion.",
            "The sensitivity table is a what-if calculation on past spend, not "
            "a forecast of future rates.",
        ],
    }


# --------------------------------------------------------------------------
# savings
# --------------------------------------------------------------------------
@dataclass
class SavingsOption:
    key: str
    title: str
    category: str
    rationale: str
    estimated_monthly_saving_base: Decimal | None
    currency: str
    confidence: float
    urgency: float
    impact_basis: str
    action_type: str | None
    action_target: str | None
    evidence: list[dict] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        monthly = self.estimated_monthly_saving_base
        return {
            "key": self.key,
            "title": self.title,
            "category": self.category,
            "rationale": self.rationale,
            "estimated_monthly_saving_base": float(monthly) if monthly is not None else None,
            "estimated_annual_saving_base": float(q2(monthly * 12)) if monthly is not None else None,
            "currency": self.currency,
            "confidence": round(self.confidence, 2),
            "urgency": round(self.urgency, 2),
            "impact_basis": self.impact_basis,
            "action_type": self.action_type,
            "action_target": self.action_target,
            "requires_user_authorization": self.action_type is not None,
            "evidence": self.evidence,
            "caveats": self.caveats,
        }


def get_savings_options(
    db: Session,
    user: User,
    today: date | None = None,
    series: list[RecurringSeries] | None = None,
) -> list[SavingsOption]:
    """See `analyze_subscriptions` for why `series` can be supplied."""
    today = today or date.today()
    fx = FxService(db)
    series_list = series if series is not None else get_recurring_series(db, user, today=today)
    findings = analyze_duplicates(series_list)
    options: list[SavingsOption] = []

    for finding in findings:
        monthly_base: Decimal | None = None
        if finding.estimated_redundant_monthly is not None:
            conv = fx.convert(
                finding.estimated_redundant_monthly, finding.currency, user.base_currency, today
            )
            monthly_base = conv.converted if conv.available else None

        if finding.finding_type == "same_service_duplicate":
            options.append(
                SavingsOption(
                    key=f"duplicate:{finding.merchants[0]}",
                    title=f"Cancel the duplicate {finding.merchants[0]} subscription",
                    category="duplicate_subscription",
                    rationale=finding.detail,
                    estimated_monthly_saving_base=monthly_base,
                    currency=user.base_currency,
                    confidence=finding.confidence,
                    urgency=0.8,
                    impact_basis=(
                        "Equals the monthly cost of the cheaper of the two "
                        "detected charges, converted at today's stored rate."
                    ),
                    action_type="cancel_subscription",
                    action_target=finding.merchants[0],
                    evidence=finding.evidence,
                    caveats=[finding.caveat],
                )
            )
        elif finding.finding_type == "overlapping_service_family":
            options.append(
                SavingsOption(
                    key=f"overlap:{'+'.join(finding.merchants)}",
                    title=f"Review {len(finding.merchants)} overlapping subscriptions",
                    category="category_overlap",
                    rationale=finding.detail,
                    estimated_monthly_saving_base=monthly_base,
                    currency=user.base_currency,
                    confidence=finding.confidence,
                    urgency=0.4,
                    impact_basis=(
                        "Assumes you drop the cheapest service in the group. "
                        "Only realised if you actually stop using it."
                    ),
                    action_type="cancel_subscription",
                    action_target=finding.merchants[0],
                    evidence=finding.evidence,
                    caveats=[finding.caveat],
                )
            )
        elif finding.finding_type == "double_charge_in_cycle":
            options.append(
                SavingsOption(
                    key=f"doublecharge:{finding.merchants[0]}",
                    title=f"Check a possible double charge from {finding.merchants[0]}",
                    category="billing_error",
                    rationale=finding.detail,
                    estimated_monthly_saving_base=None,
                    currency=user.base_currency,
                    confidence=finding.confidence,
                    urgency=0.65,
                    impact_basis=(
                        "No saving estimated: a refund depends on whether the "
                        "merchant agrees the charge was duplicated."
                    ),
                    action_type=None,
                    action_target=finding.merchants[0],
                    evidence=finding.evidence,
                    caveats=[finding.caveat],
                )
            )

    # Price increases: the saving is the increase itself, if reversible.
    for series in series_list:
        if series.status != "active":
            continue
        for change in reportable_price_changes(series):
            if change.change_amount <= 0:
                continue
            conv = fx.convert(
                change.change_amount, change.currency, user.base_currency, today
            )
            options.append(
                SavingsOption(
                    key=f"price:{series.merchant}:{change.effective_date.isoformat()}",
                    title=f"{series.merchant} went up {change.change_pct * 100:.0f}%",
                    category="price_increase",
                    rationale=(
                        f"{series.merchant} rose from {change.currency} "
                        f"{change.previous_amount:.2f} to {change.new_amount:.2f} on "
                        f"{change.effective_date.isoformat()}"
                        + (
                            " and the higher amount has been charged again since."
                            if change.confirmed_by_later_charge
                            else ", seen once so far."
                        )
                    ),
                    estimated_monthly_saving_base=conv.converted if conv.available else None,
                    currency=user.base_currency,
                    confidence=change.confidence,
                    urgency=0.55,
                    impact_basis=(
                        "Equals the size of the increase. Realised only if you "
                        "downgrade or move back to the previous plan."
                    ),
                    action_type=None,
                    action_target=series.merchant,
                    evidence=[
                        {
                            "transaction_id": t.id,
                            "date": t.posted_date.isoformat(),
                            "amount": float(t.amount),
                            "currency": t.currency,
                        }
                        for t in series.occurrences
                        if t.id in change.evidence_transaction_ids
                    ],
                    caveats=[
                        "A downgrade may reduce features; the saving is not "
                        "automatic."
                    ],
                )
            )

    # Disclosed cross-border fees.
    fx_costs = analyze_currency_costs(db, user, months=6, today=today)
    monthly_fees = Decimal(str(fx_costs["summary"]["disclosed_fees_base"])) / Decimal(6)
    if monthly_fees > 0:
        options.append(
            SavingsOption(
                key="fees:cross_border",
                title="Transfer fees are a recurring cost worth comparing",
                category="cross_border_fees",
                rationale=(
                    f"You paid {user.base_currency} "
                    f"{fx_costs['summary']['disclosed_fees_base']:.2f} in disclosed "
                    f"transfer fees over the last 6 months across "
                    f"{fx_costs['summary']['disclosed_fee_transaction_count']} transfers."
                ),
                estimated_monthly_saving_base=q2(monthly_fees),
                currency=user.base_currency,
                confidence=0.4,
                urgency=0.3,
                impact_basis=(
                    "Shows the full disclosed fee as the upper bound. Any real "
                    "saving depends on a cheaper provider existing for your "
                    "corridor, which this demo data cannot confirm."
                ),
                action_type=None,
                action_target="Cross-border transfers",
                evidence=[
                    {
                        "currency": b["currency"],
                        "disclosed_fees_base": b["disclosed_fees_base"],
                        "transaction_count": b["transaction_count"],
                    }
                    for b in fx_costs["by_currency"]
                    if b["disclosed_fees_base"] > 0
                ],
                caveats=[
                    "Only fees the statement discloses are counted; provider "
                    "exchange-rate spreads are not visible in this data."
                ],
            )
        )

    options.sort(
        key=lambda o: -(float(o.estimated_monthly_saving_base or 0) * o.confidence)
    )
    return options


# --------------------------------------------------------------------------
# bills
# --------------------------------------------------------------------------
def get_upcoming_bills(
    db: Session,
    user: User,
    days_ahead: int = 30,
    today: date | None = None,
    include_paid: bool = False,
) -> dict:
    today = today or date.today()
    days_ahead = max(1, min(days_ahead, 365))
    end = today + timedelta(days=days_ahead)
    fx = FxService(db)

    stmt = select(Bill).where(
        Bill.user_id == user.id, Bill.due_date >= today, Bill.due_date <= end
    )
    if not include_paid:
        stmt = stmt.where(Bill.status != "paid")
    rows = db.execute(stmt.order_by(Bill.due_date)).scalars().all()

    items: list[dict] = []
    total_base = Decimal("0")
    unconverted: list[dict] = []
    for bill in rows:
        conv = fx.convert(bill.amount, bill.currency, user.base_currency, bill.due_date)
        if conv.available:
            total_base += conv.converted
        else:
            unconverted.append({"name": bill.name, "currency": bill.currency, "reason": conv.note})
        items.append(
            {
                "id": bill.id,
                "name": bill.name,
                "merchant": bill.merchant_normalized,
                "category": bill.category,
                "due_date": bill.due_date.isoformat(),
                "days_until_due": (bill.due_date - today).days,
                "amount": float(bill.amount),
                "currency": bill.currency,
                "amount_base": float(conv.converted) if conv.available else None,
                "base_currency": user.base_currency,
                "status": bill.status,
                "is_recurring": bill.is_recurring,
                "autopay": bill.autopay,
                "notes": bill.notes,
                "conversion": conv.to_dict(),
            }
        )

    return {
        "as_of": today.isoformat(),
        "base_currency": user.base_currency,
        "window_days": days_ahead,
        "count": len(items),
        "total_due_base": float(q2(total_base)),
        "amounts_excluded_for_missing_rates": unconverted,
        "bills": items,
    }
