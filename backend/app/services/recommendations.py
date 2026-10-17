"""Recommendation ranking.

Combines savings options, forecast risks and bill pressure into one ordered
list. Ranking blends four signals the user can inspect on each card:

    urgency   how soon it matters
    impact    estimated money involved, normalised across the candidate set
    confidence how well the underlying detection is supported
    priority  overlap with the priorities the user stated

Each recommendation is tagged with `basis` so the UI can distinguish a figure
we calculated from one we estimated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from ..models import User
from .analysis import get_recurring_series, get_savings_options, get_upcoming_bills
from .forecast import forecast_balance

WEIGHT_URGENCY = 0.34
WEIGHT_IMPACT = 0.30
WEIGHT_CONFIDENCE = 0.22
WEIGHT_PRIORITY = 0.14

# Priority phrase -> recommendation categories it should boost.
PRIORITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "overdraft": ("cash_flow_risk", "bill_due_soon"),
    "shortfall": ("cash_flow_risk", "bill_due_soon"),
    "cash": ("cash_flow_risk", "bill_due_soon"),
    "streaming": ("duplicate_subscription", "category_overlap", "price_increase"),
    "subscription": ("duplicate_subscription", "category_overlap", "price_increase"),
    "cut": ("duplicate_subscription", "category_overlap", "price_increase"),
    "money home": ("cross_border_fees",),
    "cheaply": ("cross_border_fees",),
    "transfer": ("cross_border_fees",),
    "fees": ("cross_border_fees",),
}


@dataclass
class Recommendation:
    key: str
    title: str
    summary: str
    category: str
    basis: str                       # calculated | estimate | suggestion
    urgency: float
    confidence: float
    estimated_impact_base: Decimal | None
    currency: str
    impact_basis: str
    action_type: str | None = None
    action_target: str | None = None
    evidence: list[dict] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    priority_alignment: float = 0.0
    score: float = 0.0
    impact_normalised: float = 0.0

    def to_dict(self) -> dict:
        impact = self.estimated_impact_base
        return {
            "key": self.key,
            "title": self.title,
            "summary": self.summary,
            "category": self.category,
            "basis": self.basis,
            "rank_score": round(self.score, 4),
            "urgency": round(self.urgency, 2),
            "confidence": round(self.confidence, 2),
            "impact_normalised": round(self.impact_normalised, 2),
            "priority_alignment": round(self.priority_alignment, 2),
            "estimated_impact_base": float(impact) if impact is not None else None,
            "estimated_annual_impact_base": float(impact * 12) if impact is not None else None,
            "currency": self.currency,
            "impact_basis": self.impact_basis,
            "suggested_action": (
                {
                    "type": self.action_type,
                    "target": self.action_target,
                    "requires_user_authorization": True,
                    "executes_immediately": False,
                }
                if self.action_type
                else None
            ),
            "evidence": self.evidence,
            "caveats": self.caveats,
        }


def _priority_alignment(category: str, priorities: list[str]) -> float:
    if not priorities:
        return 0.0
    text = " ".join(priorities).lower()
    for keyword, categories in PRIORITY_KEYWORDS.items():
        if keyword in text and category in categories:
            return 1.0
    return 0.0


def build_recommendations(
    db: Session,
    user: User,
    today: date | None = None,
    horizon_days: int = 30,
    limit: int = 10,
) -> list[Recommendation]:
    today = today or date.today()
    candidates: list[Recommendation] = []

    # --- cash-flow risk ----------------------------------------------------
    series = get_recurring_series(db, user, today=today)
    forecast = forecast_balance(db, user, series, horizon_days=horizon_days, today=today)

    if forecast.shortfall_detected and forecast.first_shortfall_date:
        days_away = (forecast.first_shortfall_date - today).days
        candidates.append(
            Recommendation(
                key="risk:projected_shortfall",
                title=f"Projected shortfall on {forecast.first_shortfall_date.isoformat()}",
                summary=(
                    f"On current projections your balance first goes negative on "
                    f"{forecast.first_shortfall_date.isoformat()}, {days_away} day(s) "
                    f"from now. It reaches its lowest point of "
                    f"{user.base_currency} {forecast.minimum_balance:,.2f} on "
                    f"{forecast.minimum_balance_date.isoformat()}, leaving you "
                    f"{user.base_currency} {forecast.largest_shortfall:,.2f} short."
                ),
                category="cash_flow_risk",
                basis="calculated",
                urgency=max(0.5, 1.0 - days_away / float(max(horizon_days, 1))),
                confidence=0.8,
                estimated_impact_base=forecast.largest_shortfall,
                currency=user.base_currency,
                impact_basis=(
                    "Largest negative balance in the day-by-day projection, "
                    "combining confirmed bills, projected subscription charges "
                    "and expected income."
                ),
                action_type=None,
                action_target=None,
                evidence=[
                    e.to_dict()
                    for e in forecast.events
                    if e.direction == "outflow"
                    and e.event_date <= forecast.minimum_balance_date
                    and e.amount_base is not None
                ][:6],
                caveats=[
                    "Projected subscription charges are estimates based on past "
                    "behaviour, not confirmed debits.",
                    *( [f"{len(forecast.excluded)} item(s) are excluded because no "
                        "exchange rate was available."] if forecast.excluded else [] ),
                ],
            )
        )

    # --- imminent large bills ---------------------------------------------
    bills = get_upcoming_bills(db, user, days_ahead=14, today=today)
    opening = forecast.opening_balance or Decimal("1")
    for bill in bills["bills"]:
        if bill["amount_base"] is None:
            continue
        amount = Decimal(str(bill["amount_base"]))
        if amount < opening * Decimal("0.20"):
            continue
        days = bill["days_until_due"]
        candidates.append(
            Recommendation(
                key=f"bill:{bill['id']}",
                title=f"{bill['name']} is due in {days} day(s)",
                summary=(
                    f"{bill['currency']} {bill['amount']:,.2f}"
                    + (
                        f" (≈ {user.base_currency} {amount:,.2f})"
                        if bill["currency"] != user.base_currency
                        else ""
                    )
                    + f" due {bill['due_date']}."
                    + (" Autopay is on." if bill["autopay"] else " Autopay is off.")
                ),
                category="bill_due_soon",
                basis="calculated",
                urgency=max(0.3, 1.0 - days / 14.0),
                confidence=0.95,
                estimated_impact_base=amount,
                currency=user.base_currency,
                impact_basis="Full billed amount converted at the rate stored for the due date.",
                action_type="create_reminder",
                action_target=bill["name"],
                evidence=[{k: bill[k] for k in ("name", "due_date", "amount", "currency", "status")}],
                caveats=(
                    [] if bill["currency"] == user.base_currency
                    else ["Converted with a simulated rate; the settled amount may differ."]
                ),
            )
        )

    # --- savings opportunities --------------------------------------------
    for option in get_savings_options(db, user, today=today, series=series):
        candidates.append(
            Recommendation(
                key=option.key,
                title=option.title,
                summary=option.rationale,
                category=option.category,
                basis="estimate" if option.estimated_monthly_saving_base is not None else "suggestion",
                urgency=option.urgency,
                confidence=option.confidence,
                estimated_impact_base=option.estimated_monthly_saving_base,
                currency=option.currency,
                impact_basis=option.impact_basis,
                action_type=option.action_type,
                action_target=option.action_target,
                evidence=option.evidence,
                caveats=option.caveats,
            )
        )

    # --- rank ---------------------------------------------------------------
    priorities = user.priority_list
    impacts = [
        float(c.estimated_impact_base)
        for c in candidates
        if c.estimated_impact_base is not None
    ]
    max_impact = max(impacts) if impacts else 0.0

    for candidate in candidates:
        raw = float(candidate.estimated_impact_base or 0)
        candidate.impact_normalised = (raw / max_impact) if max_impact > 0 else 0.0
        candidate.priority_alignment = _priority_alignment(candidate.category, priorities)
        candidate.score = (
            WEIGHT_URGENCY * candidate.urgency
            + WEIGHT_IMPACT * candidate.impact_normalised
            + WEIGHT_CONFIDENCE * candidate.confidence
            + WEIGHT_PRIORITY * candidate.priority_alignment
        )

    candidates.sort(key=lambda c: -c.score)
    return candidates[:limit]
