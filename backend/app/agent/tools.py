"""The agent's tool allowlist.

Design rules enforced here:

  * The model can only name tools in `TOOL_REGISTRY`. Anything else is refused
    before any code runs.
  * Arguments are parsed by a Pydantic model with `extra="forbid"`, so unknown
    or malformed fields are rejected rather than silently ignored.
  * `user_id` is never an argument. Scope comes from the server-side
    `ToolContext`, so the model cannot address another user's records.
  * No tool performs financial arithmetic. Each one delegates to the services
    layer and returns the numbers that layer calculated.
  * Every payload states amount, currency, period and uncertainty, and is
    compacted so a long history cannot flood the context window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..models import Reminder, User
from ..services.analysis import (
    analyze_currency_costs,
    analyze_subscriptions,
    get_recurring_series,
    get_savings_options,
    get_upcoming_bills,
)
from ..services.forecast import forecast_balance
from ..services.sanitize import sanitize_for_llm

DATA_SOURCE_NOTE = "Synthetic demo data. No real bank account is connected."
MAX_LIST_ITEMS = 25
MAX_EVIDENCE_ITEMS = 3


@dataclass
class ToolContext:
    """Server-controlled execution scope. Never populated from model output."""

    db: Session
    user: User
    today: date
    _series: list | None = field(default=None, repr=False)

    def series(self) -> list:
        """Recurrence detection, computed once per request.

        Several tools need the same series, and a multi-tool answer would
        otherwise re-run the whole pipeline for each one. The context lives for
        exactly one request, so there is nothing to invalidate.
        """
        if self._series is None:
            self._series = get_recurring_series(self.db, self.user, today=self.today)
        return self._series


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# argument models
# --------------------------------------------------------------------------
class GetRecurringPaymentsArgs(ToolArgs):
    status: Literal["active", "dormant", "all"] = Field(
        default="active", description="Which series to return."
    )
    min_confidence: float = Field(
        default=0.45, ge=0.0, le=1.0,
        description="Lowest detection confidence to include, 0-1.",
    )
    limit: int = Field(default=20, ge=1, le=50, description="Maximum series to return.")


class GetUpcomingBillsArgs(ToolArgs):
    days_ahead: int = Field(
        default=30, ge=1, le=365, description="Size of the look-ahead window in days."
    )
    include_paid: bool = Field(default=False, description="Include already-paid bills.")


class ForecastBalanceArgs(ToolArgs):
    horizon_days: int = Field(
        default=30, ge=1, le=365, description="How many days forward to project."
    )
    include_projected_recurring: bool = Field(
        default=True,
        description="Include projected subscription charges as well as confirmed bills.",
    )


class AnalyzeSubscriptionsArgs(ToolArgs):
    include_dormant: bool = Field(
        default=False, description="Include series that appear to have stopped."
    )
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class AnalyzeCurrencyCostsArgs(ToolArgs):
    months: int = Field(
        default=6, ge=1, le=24, description="Months of history to analyse."
    )


class GetSavingsOptionsArgs(ToolArgs):
    limit: int = Field(default=10, ge=1, le=20)


class CreateReminderArgs(ToolArgs):
    title: str = Field(min_length=1, max_length=200)
    due_date: date = Field(description="ISO date, YYYY-MM-DD.")
    note: str = Field(default="", max_length=500)
    related_kind: Literal["bill", "subscription", "forecast", "other"] = "other"
    related_ref: str | None = Field(default=None, max_length=160)


# --------------------------------------------------------------------------
# envelope helpers
# --------------------------------------------------------------------------
def _envelope(
    tool: str,
    ctx: ToolContext,
    data: dict,
    *,
    period: dict,
    uncertainty: dict,
    headline_facts: list[dict],
) -> dict:
    return {
        "tool": tool,
        "generated_at": ctx.today.isoformat(),
        "scope": "current user only",
        "reporting_currency": ctx.user.base_currency,
        "period": period,
        "data": data,
        "headline_facts": headline_facts,
        "uncertainty": uncertainty,
        "data_source": DATA_SOURCE_NOTE,
    }


def _fact(
    label: str,
    value: Any,
    *,
    currency: str | None = None,
    basis: str = "calculated",
    period: str | None = None,
    confidence: float | None = None,
    note: str = "",
) -> dict:
    return {
        "label": label,
        "value": value,
        "currency": currency,
        "basis": basis,
        "period": period,
        "confidence": confidence,
        "note": note,
    }


def _trim_forecast_event(event: dict) -> dict:
    """One line per projected movement.

    The per-event rate and provenance notes are identical boilerplate repeated
    across every row; they are stated once in the envelope's uncertainty block
    instead. The original amount is only worth carrying when it differs from
    the reporting currency.
    """
    trimmed = {
        "date": event.get("date"),
        "label": event.get("label"),
        "kind": event.get("kind"),
        "direction": event.get("direction"),
        "amount_base": event.get("amount_base"),
        "certainty": event.get("certainty"),
    }
    if event.get("conversion_status") not in {"ok", "same_currency"}:
        trimmed["amount_base"] = None
        trimmed["conversion_status"] = event.get("conversion_status")
    elif event.get("currency_original") and event.get("conversion_status") == "ok":
        trimmed["amount_original"] = event.get("amount_original")
        trimmed["currency_original"] = event.get("currency_original")
    if event.get("rate_stale"):
        trimmed["rate_stale"] = True
    return trimmed


def _trim_subscription(entry: dict) -> dict:
    """Shrink a series to what the model can actually reason with.

    Two things are deliberately withheld. Individual transaction rows go to the
    UI, not here: the model cannot verify an id and should be citing the count
    and the date range instead, which it gets. And a series we could not
    establish as recurring is reduced to a stub, because the only honest thing
    to say about it is that the evidence is thin.
    """
    observed = {
        "charges_observed": entry.get("occurrence_count"),
        "first_seen": entry.get("first_seen"),
        "last_seen": entry.get("last_seen"),
    }

    if entry.get("verdict") == "insufficient_evidence":
        return {
            "merchant": entry.get("merchant"),
            "currency": entry.get("currency"),
            "verdict": "insufficient_evidence",
            "confidence": entry.get("confidence"),
            "observed": observed,
            "note": "Not established as recurring; report it as unconfirmed.",
        }

    keep = {
        k: entry[k]
        for k in (
            "merchant", "currency", "cadence", "latest_amount", "monthly_equivalent",
            "monthly_equivalent_base", "next_expected_date", "status", "confidence",
            "verdict", "service_family",
        )
        if k in entry
    }
    keep["observed"] = observed
    keep["reasons"] = entry.get("reasons", [])[:3]
    if entry.get("price_changes"):
        keep["price_changes"] = entry["price_changes"]
    return keep


# --------------------------------------------------------------------------
# tool implementations
# --------------------------------------------------------------------------
def tool_get_recurring_payments(ctx: ToolContext, args: GetRecurringPaymentsArgs) -> dict:
    series = ctx.series()
    selected = [
        s for s in series
        if s.confidence >= args.min_confidence
        and (args.status == "all" or s.status == args.status)
    ][: args.limit]

    subs = analyze_subscriptions(
        ctx.db, ctx.user, today=ctx.today, include_dormant=True, series=series
    )
    base_by_merchant = {
        (s["merchant"], s["account_id"]): s.get("monthly_equivalent_base")
        for s in subs["subscriptions"]
    }

    items = []
    for s in selected:
        entry = _trim_subscription(s.to_dict())
        entry["monthly_equivalent_base"] = base_by_merchant.get((s.merchant, s.account_id))
        items.append(entry)

    low_confidence = [i["merchant"] for i in items if i["verdict"] == "possible_recurring"]
    return _envelope(
        "get_recurring_payments",
        ctx,
        {"count": len(items), "series": items},
        period={"as_of": ctx.today.isoformat(), "lookback_days": 420},
        uncertainty={
            "verdict_scale": "likely_recurring > possible_recurring > insufficient_evidence",
            "possible_only": low_confidence,
            "guidance": (
                "Series marked possible_recurring are not confirmed subscriptions. "
                "Describe them as 'looks like' rather than as fact."
            ),
        },
        headline_facts=[
            _fact(
                "Active detected recurring payments",
                len(items),
                period=f"as of {ctx.today.isoformat()}",
            )
        ],
    )


def tool_get_upcoming_bills(ctx: ToolContext, args: GetUpcomingBillsArgs) -> dict:
    result = get_upcoming_bills(
        ctx.db, ctx.user, days_ahead=args.days_ahead,
        today=ctx.today, include_paid=args.include_paid,
    )
    bills = [
        {
            k: b[k]
            for k in (
                "name", "category", "due_date", "days_until_due", "amount",
                "currency", "amount_base", "status", "autopay",
            )
        }
        for b in result["bills"][:MAX_LIST_ITEMS]
    ]
    return _envelope(
        "get_upcoming_bills",
        ctx,
        {
            "count": result["count"],
            "total_due_base": result["total_due_base"],
            "bills": bills,
        },
        period={
            "start": ctx.today.isoformat(),
            "end": (ctx.today + timedelta(days=args.days_ahead)).isoformat(),
            "days": args.days_ahead,
        },
        uncertainty={
            "excluded_for_missing_rates": result["amounts_excluded_for_missing_rates"],
            "guidance": (
                "Bill amounts are confirmed. Converted figures use simulated "
                "rates and may differ from the settled amount."
            ),
        },
        headline_facts=[
            _fact(
                "Total due",
                result["total_due_base"],
                currency=ctx.user.base_currency,
                period=f"next {args.days_ahead} days",
            ),
            _fact("Bill count", result["count"], period=f"next {args.days_ahead} days"),
        ],
    )


def tool_forecast_balance(ctx: ToolContext, args: ForecastBalanceArgs) -> dict:
    series = ctx.series()
    result = forecast_balance(
        ctx.db, ctx.user, series,
        horizon_days=args.horizon_days, today=ctx.today,
        include_projected_recurring=args.include_projected_recurring,
    )
    payload = result.to_dict()
    # The day-by-day array is for charts, not for the model.
    payload.pop("daily", None)
    payload.pop("opening_balance_breakdown", None)
    all_events = payload["events"]
    payload["events"] = [_trim_forecast_event(e) for e in all_events[:MAX_LIST_ITEMS]]
    payload["events_shown"] = len(payload["events"])
    payload["events_total"] = len(all_events)

    facts = [
        _fact("Opening balance", payload["opening_balance"], currency=result.base_currency),
        _fact(
            "Projected closing balance", payload["closing_balance"],
            currency=result.base_currency, basis="estimate",
            period=f"{result.start_date.isoformat()} to {result.end_date.isoformat()}",
        ),
        _fact(
            "Lowest projected balance", payload["minimum_balance"],
            currency=result.base_currency, basis="estimate",
            period=f"on {payload['minimum_balance_date']}",
        ),
    ]
    if result.shortfall_detected:
        facts.append(
            _fact(
                "Projected shortfall", payload["largest_shortfall"],
                currency=result.base_currency, basis="estimate",
                period=f"first on {payload['first_shortfall_date']}",
                note="Balance is projected to go negative.",
            )
        )

    return _envelope(
        "forecast_balance",
        ctx,
        payload,
        period=payload["period"],
        uncertainty={
            "assumptions": result.assumptions,
            "excluded_items": result.excluded,
            "guidance": (
                "Events marked 'projected' are inferred from past behaviour. "
                "Only events marked 'confirmed' have a known due date and amount. "
                "Every converted figure uses a simulated rate; an event flagged "
                "'rate_stale' used a rate older than its own date, so treat that "
                "converted amount as an estimate."
            ),
        },
        headline_facts=facts,
    )


def tool_analyze_subscriptions(ctx: ToolContext, args: AnalyzeSubscriptionsArgs) -> dict:
    result = analyze_subscriptions(
        ctx.db, ctx.user, today=ctx.today,
        min_confidence=args.min_confidence, include_dormant=args.include_dormant,
        series=ctx.series(),
    )
    data = {
        "summary": result["summary"],
        "subscriptions": [
            _trim_subscription(s) for s in result["subscriptions"][:MAX_LIST_ITEMS]
        ],
        "duplicate_findings": [
            {
                "finding_type": f["finding_type"],
                "title": f["title"],
                "detail": f["detail"],
                "merchants": f["merchants"],
                "estimated_redundant_monthly": f["estimated_redundant_monthly"],
                "currency": f["currency"],
                "confidence": f["confidence"],
                "verdict": f["verdict"],
                "caveat": f["caveat"],
            }
            for f in result["duplicate_findings"]
        ],
        "price_changes": result["price_changes"][:MAX_LIST_ITEMS],
        "methodology": result["methodology"],
    }
    return _envelope(
        "analyze_subscriptions",
        ctx,
        data,
        period={"as_of": ctx.today.isoformat(), "lookback_days": 420},
        uncertainty={
            "duplicate_verdicts": "likely > possible > informational",
            "guidance": (
                "An 'informational' overlap means several services cover the "
                "same need, which is often intentional. Do not call it an error."
            ),
            "excluded_for_missing_rates": result["summary"][
                "amounts_excluded_for_missing_rates"
            ],
        },
        headline_facts=[
            _fact(
                "Estimated monthly subscription cost",
                result["summary"]["estimated_monthly_total_base"],
                currency=ctx.user.base_currency, basis="estimate",
                period="per month",
                note="Each cadence normalised to a monthly figure.",
            ),
            _fact("Duplicate or overlap findings", result["summary"]["duplicate_findings"]),
            _fact("Price changes detected", result["summary"]["price_changes_detected"]),
        ],
    )


def tool_analyze_currency_costs(ctx: ToolContext, args: AnalyzeCurrencyCostsArgs) -> dict:
    result = analyze_currency_costs(ctx.db, ctx.user, months=args.months, today=ctx.today)
    data = {
        "summary": result["summary"],
        "by_currency": result["by_currency"][:MAX_LIST_ITEMS],
        "fx_sensitivity_whatif": result["fx_sensitivity_whatif"],
        "unconvertible_transactions": result["unconvertible_transactions"][:MAX_EVIDENCE_ITEMS],
    }
    return _envelope(
        "analyze_currency_costs",
        ctx,
        data,
        period=result["period"],
        uncertainty={
            "notes": result["notes"],
            "guidance": (
                "Only disclosed fees are counted. Do not claim a total cost of "
                "currency conversion, because provider spreads are not in this data. "
                "When the user asks about a currency drop or strengthening, quote "
                "fx_sensitivity_whatif and label it as a what-if on past foreign "
                "spend — not a prediction of future rates."
            ),
        },
        headline_facts=[
            _fact(
                "Foreign-currency spend",
                result["summary"]["foreign_currency_spend_base"],
                currency=ctx.user.base_currency,
                period=f"last {args.months} months",
            ),
            _fact(
                "Disclosed transfer fees",
                result["summary"]["disclosed_fees_base"],
                currency=ctx.user.base_currency,
                period=f"last {args.months} months",
            ),
            *[
                _fact(
                    row["scenario"],
                    row["monthly_impact_base"],
                    currency=ctx.user.base_currency,
                    basis="estimate",
                    period="what-if on recent foreign spend / month",
                    note="Illustrative sensitivity, not a market forecast.",
                )
                for row in result["fx_sensitivity_whatif"]
                if "-10%" in row.get("scenario", "") or "+10%" in row.get("scenario", "")
            ],
        ],
    )


def tool_get_savings_options(ctx: ToolContext, args: GetSavingsOptionsArgs) -> dict:
    options = get_savings_options(
        ctx.db, ctx.user, today=ctx.today, series=ctx.series()
    )[: args.limit]
    payload = [o.to_dict() for o in options]
    for option in payload:
        option["evidence"] = option["evidence"][:MAX_EVIDENCE_ITEMS]

    total = sum(o["estimated_monthly_saving_base"] or 0 for o in payload)
    return _envelope(
        "get_savings_options",
        ctx,
        {"count": len(payload), "options": payload},
        period={"as_of": ctx.today.isoformat()},
        uncertainty={
            "guidance": (
                "Every saving is conditional on the user actually making the "
                "change. Quote the impact_basis and caveats alongside any number."
            )
        },
        headline_facts=[
            _fact(
                "Maximum combined monthly saving",
                round(total, 2),
                currency=ctx.user.base_currency, basis="estimate",
                period="per month",
                note="Upper bound assuming every option is acted on.",
            )
        ],
    )


def tool_create_reminder(ctx: ToolContext, args: CreateReminderArgs) -> dict:
    """State-changing, so it lands in `pending_confirmation`.

    Nothing is scheduled until the user confirms it in the UI.
    """
    if args.due_date < ctx.today - timedelta(days=1):
        return _envelope(
            "create_reminder",
            ctx,
            {"created": False, "reason": "The due date is in the past."},
            period={"as_of": ctx.today.isoformat()},
            uncertainty={"guidance": "Ask the user for a future date."},
            headline_facts=[],
        )

    reminder = Reminder(
        user_id=ctx.user.id,
        title=args.title,
        due_date=args.due_date,
        note=args.note,
        related_kind=args.related_kind,
        related_ref=args.related_ref,
        created_by="assistant",
        status="pending_confirmation",
    )
    ctx.db.add(reminder)
    ctx.db.flush()

    return _envelope(
        "create_reminder",
        ctx,
        {
            "created": True,
            "reminder_id": reminder.id,
            "title": reminder.title,
            "due_date": reminder.due_date.isoformat(),
            "status": "pending_confirmation",
            "requires_user_confirmation": True,
        },
        period={"due_date": reminder.due_date.isoformat()},
        uncertainty={
            "guidance": (
                "The reminder is a draft. Tell the user it is waiting for their "
                "confirmation in the Reminders panel and is not active yet."
            )
        },
        headline_facts=[
            _fact(
                "Draft reminder created", reminder.title,
                period=reminder.due_date.isoformat(), basis="action",
                note="Pending user confirmation.",
            )
        ],
    )


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[ToolArgs]
    handler: Callable[[ToolContext, Any], dict]
    mutates_state: bool = False


TOOL_REGISTRY: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in [
        ToolSpec(
            name="get_recurring_payments",
            description=(
                "List detected recurring payments with cadence, latest amount, "
                "next expected date, confidence and verdict. Use for questions "
                "about what is charged regularly."
            ),
            args_model=GetRecurringPaymentsArgs,
            handler=tool_get_recurring_payments,
        ),
        ToolSpec(
            name="get_upcoming_bills",
            description=(
                "List bills due within a window, with amounts in their original "
                "currency and the reporting-currency equivalent."
            ),
            args_model=GetUpcomingBillsArgs,
            handler=tool_get_upcoming_bills,
        ),
        ToolSpec(
            name="forecast_balance",
            description=(
                "Project the balance over a horizon using confirmed bills, "
                "projected recurring charges and expected income. Returns the "
                "lowest projected balance and any shortfall. Use for questions "
                "about affordability or running out of money."
            ),
            args_model=ForecastBalanceArgs,
            handler=tool_forecast_balance,
        ),
        ToolSpec(
            name="analyze_subscriptions",
            description=(
                "Full subscription analysis: totals, duplicate and overlapping "
                "services, and detected price changes with evidence."
            ),
            args_model=AnalyzeSubscriptionsArgs,
            handler=tool_analyze_subscriptions,
        ),
        ToolSpec(
            name="analyze_currency_costs",
            description=(
                "Break down spending by currency with dated rates and disclosed "
                "transfer fees. ALWAYS call this for FX / exchange-rate / cedi / "
                "GHS / remittance-fee questions, including what-if questions like "
                "'what if the cedi drops 10%'. The result includes "
                "fx_sensitivity_whatif: estimated monthly impact of ±5% and ±10% "
                "moves against the reporting currency on recent foreign spend. "
                "That table is a what-if on past spend, not a market forecast."
            ),
            args_model=AnalyzeCurrencyCostsArgs,
            handler=tool_analyze_currency_costs,
        ),
        ToolSpec(
            name="get_savings_options",
            description=(
                "Ranked savings opportunities, each with an estimated monthly "
                "impact, confidence, the basis for the figure, and caveats."
            ),
            args_model=GetSavingsOptionsArgs,
            handler=tool_get_savings_options,
        ),
        ToolSpec(
            name="create_reminder",
            description=(
                "Draft a reminder for the user. The reminder is created in a "
                "pending state and only becomes active once the user confirms "
                "it in the interface."
            ),
            args_model=CreateReminderArgs,
            handler=tool_create_reminder,
            mutates_state=True,
        ),
    ]
}

ALLOWED_TOOL_NAMES = frozenset(TOOL_REGISTRY)


def _json_schema(model: type[ToolArgs]) -> dict:
    schema = model.model_json_schema()
    schema.pop("title", None)
    schema["additionalProperties"] = False
    return schema


def tool_definitions() -> list[dict]:
    """Tool schemas in OpenAI Responses API format."""
    return [
        {
            "type": "function",
            "name": spec.name,
            "description": spec.description,
            "parameters": _json_schema(spec.args_model),
        }
        for spec in TOOL_REGISTRY.values()
    ]


class ToolValidationError(ValueError):
    """Argument validation failed; the message is safe to return to the model."""


def execute_tool(ctx: ToolContext, name: str, raw_arguments: dict) -> dict:
    """Validate and run one tool. Raises on an unknown name or bad arguments."""
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        raise ToolValidationError(
            f"Unknown tool '{name}'. Allowed tools: {', '.join(sorted(ALLOWED_TOOL_NAMES))}."
        )
    if not isinstance(raw_arguments, dict):
        raise ToolValidationError("Tool arguments must be a JSON object.")
    # Defence in depth: scope can only come from ToolContext.
    for forbidden in ("user_id", "user", "email", "account_id"):
        if forbidden in raw_arguments:
            raise ToolValidationError(
                f"'{forbidden}' is not an accepted argument. Scope is set by the server."
            )

    try:
        args = spec.args_model.model_validate(raw_arguments)
    except Exception as exc:  # pydantic ValidationError
        raise ToolValidationError(_format_validation_error(exc)) from exc

    # Scrub account-like digits and emails before anything reaches the model.
    return sanitize_for_llm(spec.handler(ctx, args))


def _format_validation_error(exc: Exception) -> str:
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return "Invalid arguments."
    parts = []
    for error in errors()[:5]:
        location = ".".join(str(p) for p in error.get("loc", ())) or "arguments"
        parts.append(f"{location}: {error.get('msg', 'invalid')}")
    return "Invalid arguments -> " + "; ".join(parts)


def summarise_result(name: str, payload: dict) -> str:
    """One-line, non-sensitive summary for the audit log and UI trace."""
    facts = payload.get("headline_facts") or []
    if not facts:
        return f"{name} returned no headline figures."
    first = facts[0]
    currency = f"{first['currency']} " if first.get("currency") else ""
    return f"{first['label']}: {currency}{first['value']}"


def _decimal_safe(value: Any) -> Any:  # pragma: no cover - json fallback
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"not serialisable: {type(value)}")
