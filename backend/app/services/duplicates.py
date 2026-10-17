"""Duplicate and overlapping subscription detection.

Three distinct signals, reported separately because they mean different things:

  same_service_duplicate   the same service appears to be billed twice (e.g. on
                           two cards, or in two currencies)
  double_charge_in_cycle   two near-identical charges from one merchant landed
                           far too close together for the observed cycle
  overlapping_service_family
                           several different services cover the same need
                           (two video streamers, two cloud-storage plans)

Only the first is treated as a probable error. The third is explicitly framed
as "may well be intentional" because plenty of people keep two of these on
purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from .recurring import CADENCE_BUCKETS, RecurringSeries, TxnRecord

# Two charges within this fraction of the expected cycle are suspiciously close.
CLOSE_CHARGE_CYCLE_FRACTION = 0.35
CLOSE_CHARGE_AMOUNT_TOLERANCE = Decimal("0.05")  # 5%


@dataclass
class DuplicateFinding:
    finding_type: str
    title: str
    detail: str
    merchants: list[str]
    currency: str
    estimated_redundant_monthly: Decimal | None
    confidence: float
    verdict: str                 # likely | possible | informational
    evidence: list[dict] = field(default_factory=list)
    caveat: str = ""

    def to_dict(self) -> dict:
        return {
            "finding_type": self.finding_type,
            "title": self.title,
            "detail": self.detail,
            "merchants": self.merchants,
            "currency": self.currency,
            "estimated_redundant_monthly": float(self.estimated_redundant_monthly)
            if self.estimated_redundant_monthly is not None
            else None,
            "confidence": round(self.confidence, 2),
            "verdict": self.verdict,
            "evidence": self.evidence,
            "caveat": self.caveat,
        }


def _series_evidence(series: RecurringSeries) -> dict:
    return {
        "merchant": series.merchant,
        "account_id": series.account_id,
        "currency": series.currency,
        "cadence": series.cadence,
        "latest_amount": float(series.latest_amount),
        "monthly_equivalent": float(round(series.monthly_equivalent, 2)),
        "last_seen": series.last_seen.isoformat(),
        "occurrence_count": len(series.occurrences),
        "detection_confidence": round(series.confidence, 2),
    }


def _considered(series: RecurringSeries) -> bool:
    """Only reasonably-supported active series can imply a duplicate."""
    return series.status == "active" and series.verdict in {
        "likely_recurring",
        "possible_recurring",
    }


def find_same_service_duplicates(
    series_list: list[RecurringSeries],
) -> list[DuplicateFinding]:
    by_merchant: dict[str, list[RecurringSeries]] = {}
    for s in series_list:
        if _considered(s):
            by_merchant.setdefault(s.merchant, []).append(s)

    findings: list[DuplicateFinding] = []
    for merchant, group in by_merchant.items():
        if len(group) < 2:
            continue

        group.sort(key=lambda s: s.monthly_equivalent)
        cheaper = group[0]
        currencies = {s.currency for s in group}
        accounts = {s.account_id for s in group}

        # Same currency AND same account would be odd; across accounts or
        # currencies is the classic "signed up twice" pattern.
        confidence = 0.85 if len(accounts) > 1 else 0.7
        confidence = min(confidence, max(s.confidence for s in group))

        if len(currencies) == 1:
            redundant = cheaper.monthly_equivalent
            currency = cheaper.currency
            money_note = ""
        else:
            redundant = cheaper.monthly_equivalent
            currency = cheaper.currency
            money_note = (
                " The two charges are in different currencies, so compare them "
                "in your reporting currency before deciding."
            )

        findings.append(
            DuplicateFinding(
                finding_type="same_service_duplicate",
                title=f"{merchant} looks like it is being billed twice",
                detail=(
                    f"{len(group)} separate recurring {merchant} charges are active "
                    f"across {len(accounts)} account(s)." + money_note
                ),
                merchants=[merchant],
                currency=currency,
                estimated_redundant_monthly=redundant,
                confidence=confidence,
                verdict="likely" if confidence >= 0.7 else "possible",
                evidence=[_series_evidence(s) for s in group],
                caveat=(
                    "Savings assume you keep the more expensive plan and cancel "
                    "the cheaper duplicate. Confirm both charges are really for "
                    "the same account before cancelling."
                ),
            )
        )
    return findings


def find_double_charges(
    series_list: list[RecurringSeries],
) -> list[DuplicateFinding]:
    findings: list[DuplicateFinding] = []
    for series in series_list:
        if not _considered(series):
            continue
        nominal = CADENCE_BUCKETS.get(
            series.cadence, (0, 0, int(series.median_interval_days) or 30)
        )[2]
        if nominal <= 0:
            continue
        window = max(1, int(nominal * CLOSE_CHARGE_CYCLE_FRACTION))

        for prev, curr in zip(series.occurrences, series.occurrences[1:]):
            gap = (curr.posted_date - prev.posted_date).days
            if gap > window or prev.amount <= 0:
                continue
            if abs(curr.amount - prev.amount) / prev.amount > CLOSE_CHARGE_AMOUNT_TOLERANCE:
                continue
            findings.append(
                DuplicateFinding(
                    finding_type="double_charge_in_cycle",
                    title=f"Two near-identical {series.merchant} charges {gap} days apart",
                    detail=(
                        f"{series.merchant} charged {curr.currency} "
                        f"{prev.amount:.2f} and {curr.amount:.2f} only {gap} days "
                        f"apart, against an expected {series.cadence} cycle."
                    ),
                    merchants=[series.merchant],
                    currency=series.currency,
                    estimated_redundant_monthly=None,
                    confidence=0.6,
                    verdict="possible",
                    evidence=[
                        {
                            "transaction_id": t.id,
                            "date": t.posted_date.isoformat(),
                            "amount": float(t.amount),
                            "currency": t.currency,
                            "description": t.description,
                        }
                        for t in (prev, curr)
                    ],
                    caveat=(
                        "This can be a genuine duplicate charge, a plan change, or "
                        "a legitimate second purchase. It is worth checking, not "
                        "proof of an error."
                    ),
                )
            )
    return findings


def find_family_overlaps(
    series_list: list[RecurringSeries],
) -> list[DuplicateFinding]:
    by_family: dict[str, list[RecurringSeries]] = {}
    for s in series_list:
        if _considered(s) and s.family:
            by_family.setdefault(s.family, []).append(s)

    findings: list[DuplicateFinding] = []
    for family, group in by_family.items():
        distinct = {s.merchant for s in group}
        if len(distinct) < 2:
            continue
        group.sort(key=lambda s: s.monthly_equivalent)
        cheapest = group[0]
        label = family.replace("_", " ")
        findings.append(
            DuplicateFinding(
                finding_type="overlapping_service_family",
                title=f"{len(distinct)} overlapping {label} subscriptions",
                detail=(
                    f"You have active {label} subscriptions with "
                    f"{', '.join(sorted(distinct))}. Dropping the least-used one "
                    "would remove the overlap."
                ),
                merchants=sorted(distinct),
                currency=cheapest.currency,
                estimated_redundant_monthly=cheapest.monthly_equivalent,
                confidence=0.5,
                verdict="informational",
                evidence=[_series_evidence(s) for s in group],
                caveat=(
                    "Keeping more than one service in this category is often "
                    "deliberate. This is a prompt to review, not a problem we "
                    "have confirmed."
                ),
            )
        )
    return findings


def analyze_duplicates(series_list: list[RecurringSeries]) -> list[DuplicateFinding]:
    findings = (
        find_same_service_duplicates(series_list)
        + find_double_charges(series_list)
        + find_family_overlaps(series_list)
    )
    findings.sort(key=lambda f: -f.confidence)
    return findings


def find_near_duplicate_transactions(
    transactions: list[TxnRecord], window_days: int = 3
) -> list[dict]:
    """Raw-transaction level duplicate scan, independent of any series."""
    by_merchant: dict[str, list[TxnRecord]] = {}
    for t in transactions:
        if t.direction == "debit":
            by_merchant.setdefault(t.merchant, []).append(t)

    hits: list[dict] = []
    for merchant, items in by_merchant.items():
        items.sort(key=lambda t: t.posted_date)
        for prev, curr in zip(items, items[1:]):
            if curr.posted_date - prev.posted_date > timedelta(days=window_days):
                continue
            if prev.amount <= 0 or prev.currency != curr.currency:
                continue
            if abs(curr.amount - prev.amount) / prev.amount > CLOSE_CHARGE_AMOUNT_TOLERANCE:
                continue
            hits.append(
                {
                    "merchant": merchant,
                    "currency": curr.currency,
                    "amount": float(curr.amount),
                    "days_apart": (curr.posted_date - prev.posted_date).days,
                    "transaction_ids": [prev.id, curr.id],
                }
            )
    return hits
