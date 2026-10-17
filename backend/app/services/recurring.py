"""Recurring-payment detection and subscription price-change analysis.

Deliberately evidence-first. The engine never returns a bare "this is a
subscription" boolean: every series carries the transactions that support it,
the measured cadence, the measured amount stability, a 0-1 confidence score and
a verdict of `likely_recurring` / `possible_recurring` / `insufficient_evidence`.

Pure functions over plain dataclasses, so the behaviour is unit-testable
without a database.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

# Cadence name -> (min_days, max_days, nominal_days)
CADENCE_BUCKETS: dict[str, tuple[int, int, int]] = {
    "weekly": (6, 8, 7),
    "biweekly": (12, 16, 14),
    "monthly": (26, 35, 30),
    "bimonthly": (55, 68, 61),
    "quarterly": (84, 98, 91),
    "semiannual": (172, 200, 182),
    "annual": (350, 380, 365),
}

MIN_OCCURRENCES = 2
LIKELY_THRESHOLD = 0.70
POSSIBLE_THRESHOLD = 0.45

# A series is considered dormant once it has missed ~1.6 cycles.
DORMANT_CYCLE_FACTOR = 1.6

# Price-change sensitivity: ignore sub-1% / sub-0.50 wobble (FX dust, rounding).
PRICE_CHANGE_MIN_PCT = Decimal("0.01")
PRICE_CHANGE_MIN_ABS = Decimal("0.50")

# A series that normally wobbles needs a bigger move before the shift means
# anything. The threshold is lifted to a multiple of the series' own typical
# charge-to-charge variation, but only once there are enough gaps to estimate
# that variation honestly.
#
# The multiplier is calibrated, not derived: across a dozen charges the largest
# routine swing tends to run two to three times the median one, so a smaller
# factor reports jitter as repricing. Erring high costs us only the detection
# of sub-noise price rises, which we could not evidence to a user anyway.
PRICE_CHANGE_NOISE_MULTIPLIER = Decimal("4")
MIN_DIFFS_FOR_NOISE_ESTIMATE = 5

# A level shift is only meaningful on a series whose amount is normally steady.
# Groceries and usage-based utility bills move every month by nature; calling
# that a "price change" would be wrong, so they are gated out of reporting.
PRICE_CHANGE_MIN_STABILITY = 0.70


@dataclass(frozen=True)
class TxnRecord:
    """Minimal transaction shape the detector needs."""

    id: int
    posted_date: date
    amount: Decimal          # positive magnitude of the outflow
    currency: str
    merchant: str            # canonical merchant key
    account_id: int
    description: str = ""
    family: str | None = None
    direction: str = "debit"


@dataclass
class PriceChange:
    merchant: str
    currency: str
    previous_amount: Decimal
    new_amount: Decimal
    change_amount: Decimal
    change_pct: float
    effective_date: date
    confidence: float
    confirmed_by_later_charge: bool
    evidence_transaction_ids: list[int]

    def to_dict(self) -> dict:
        return {
            "merchant": self.merchant,
            "currency": self.currency,
            "previous_amount": float(self.previous_amount),
            "new_amount": float(self.new_amount),
            "change_amount": float(self.change_amount),
            "change_pct": round(self.change_pct * 100, 2),
            "direction": "increase" if self.change_amount > 0 else "decrease",
            "effective_date": self.effective_date.isoformat(),
            "annualized_impact": float(self.change_amount * 12)
            if self.change_amount is not None
            else None,
            "confidence": round(self.confidence, 2),
            "confirmed_by_later_charge": self.confirmed_by_later_charge,
            "evidence_transaction_ids": self.evidence_transaction_ids,
            "basis": (
                "Annualized impact assumes the monthly cadence observed in the "
                "transaction history continues unchanged."
            ),
        }


@dataclass
class RecurringSeries:
    merchant: str
    currency: str
    account_id: int
    family: str | None
    occurrences: list[TxnRecord]
    cadence: str
    median_interval_days: float
    interval_regularity: float     # 0-1
    amount_stability: float        # 0-1
    typical_amount: Decimal
    latest_amount: Decimal
    first_seen: date
    last_seen: date
    confidence: float
    verdict: str
    status: str                    # active | dormant
    next_expected_date: date | None
    price_changes: list[PriceChange] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def monthly_equivalent(self) -> Decimal:
        """Latest charge normalised to a monthly figure for comparability."""
        nominal = CADENCE_BUCKETS.get(self.cadence, (0, 0, int(self.median_interval_days) or 30))[2]
        if nominal <= 0:
            return self.latest_amount
        return (self.latest_amount * Decimal(30)) / Decimal(nominal)

    @property
    def annual_equivalent(self) -> Decimal:
        nominal = CADENCE_BUCKETS.get(self.cadence, (0, 0, int(self.median_interval_days) or 30))[2]
        if nominal <= 0:
            return self.latest_amount * 12
        return (self.latest_amount * Decimal(365)) / Decimal(nominal)

    def to_dict(self) -> dict:
        return {
            "merchant": self.merchant,
            "currency": self.currency,
            "account_id": self.account_id,
            "service_family": self.family,
            "cadence": self.cadence,
            "median_interval_days": round(self.median_interval_days, 1),
            "occurrence_count": len(self.occurrences),
            "typical_amount": float(self.typical_amount),
            "latest_amount": float(self.latest_amount),
            "monthly_equivalent": float(round(self.monthly_equivalent, 2)),
            "annual_equivalent": float(round(self.annual_equivalent, 2)),
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "next_expected_date": self.next_expected_date.isoformat()
            if self.next_expected_date
            else None,
            "status": self.status,
            "confidence": round(self.confidence, 2),
            "verdict": self.verdict,
            "interval_regularity": round(self.interval_regularity, 2),
            "amount_stability": round(self.amount_stability, 2),
            "reasons": self.reasons,
            "price_changes": [pc.to_dict() for pc in self.price_changes],
            "evidence": [
                {
                    "transaction_id": t.id,
                    "date": t.posted_date.isoformat(),
                    "amount": float(t.amount),
                    "currency": t.currency,
                    "description": t.description,
                }
                for t in self.occurrences
            ],
        }


# --------------------------------------------------------------------------
# cadence helpers
# --------------------------------------------------------------------------
def classify_cadence(median_days: float) -> str:
    for name, (lo, hi, _) in CADENCE_BUCKETS.items():
        if lo <= median_days <= hi:
            return name
    return "irregular"


def _add_months(start: date, months: int) -> date:
    """Advance by whole months, clamping to the end of a short month."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = start.day
    while day > 0:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1
    return start


def project_next_date(last_seen: date, cadence: str, median_days: float) -> date:
    """Next expected charge date for a cadence."""
    if cadence == "monthly":
        return _add_months(last_seen, 1)
    if cadence == "bimonthly":
        return _add_months(last_seen, 2)
    if cadence == "quarterly":
        return _add_months(last_seen, 3)
    if cadence == "semiannual":
        return _add_months(last_seen, 6)
    if cadence == "annual":
        return _add_months(last_seen, 12)
    step = CADENCE_BUCKETS.get(cadence, (0, 0, 0))[2] or int(round(median_days)) or 30
    return last_seen + timedelta(days=step)


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------
def _interval_regularity(intervals: list[int]) -> float:
    """1.0 = perfectly even spacing; decays with relative deviation."""
    if len(intervals) < 2:
        return 0.5  # one gap tells us little either way
    median = statistics.median(intervals)
    if median <= 0:
        return 0.0
    mad = statistics.fmean(abs(i - median) for i in intervals)
    # 25% average drift from the median scores 0.
    return max(0.0, min(1.0, 1.0 - (mad / median) / 0.25))


def _amount_stability(amounts: list[Decimal]) -> float:
    if len(amounts) < 2:
        return 0.5
    values = [float(a) for a in amounts]
    mean = statistics.fmean(values)
    if mean <= 0:
        return 0.0
    spread = statistics.pstdev(values) / mean
    # 20% coefficient of variation scores 0.
    return max(0.0, min(1.0, 1.0 - spread / 0.20))


def _score(
    intervals: list[int],
    amounts: list[Decimal],
    cadence: str,
    occurrence_count: int,
) -> tuple[float, float, float, list[str]]:
    regularity = _interval_regularity(intervals)
    stability = _amount_stability(amounts)
    count_factor = min(1.0, (occurrence_count - 1) / 4.0)
    cadence_known = 1.0 if cadence != "irregular" else 0.0

    confidence = (
        0.38 * regularity
        + 0.24 * stability
        + 0.26 * count_factor
        + 0.12 * cadence_known
    )

    reasons: list[str] = []
    reasons.append(
        f"{occurrence_count} charges observed"
        + (f" roughly every {round(statistics.median(intervals))} days" if intervals else "")
    )
    if cadence_known:
        reasons.append(f"Spacing matches a {cadence} cycle")
    else:
        reasons.append("Spacing does not match a standard billing cycle")
    if stability >= 0.8:
        reasons.append("Charge amount is consistent between occurrences")
    elif stability >= 0.4:
        reasons.append("Charge amount varies moderately between occurrences")
    else:
        reasons.append("Charge amount varies a lot, which weakens the signal")
    if occurrence_count < 3:
        reasons.append("Only a short history is available, so confidence is capped")

    return min(confidence, 1.0), regularity, stability, reasons


def verdict_for(confidence: float, occurrence_count: int) -> str:
    if occurrence_count < MIN_OCCURRENCES:
        return "insufficient_evidence"
    if confidence >= LIKELY_THRESHOLD:
        return "likely_recurring"
    if confidence >= POSSIBLE_THRESHOLD:
        return "possible_recurring"
    return "insufficient_evidence"


# --------------------------------------------------------------------------
# price changes
# --------------------------------------------------------------------------
def _typical_variation(occurrences: list[TxnRecord]) -> Decimal:
    """Median relative difference between consecutive charges.

    Near zero for a fixed-price subscription; substantial for a metered bill.
    """
    diffs: list[float] = []
    for prev, curr in zip(occurrences, occurrences[1:]):
        if prev.amount > 0:
            diffs.append(float(abs(curr.amount - prev.amount) / prev.amount))
    if len(diffs) < MIN_DIFFS_FOR_NOISE_ESTIMATE:
        return Decimal("0")
    return Decimal(str(statistics.median(diffs)))


def price_change_threshold(occurrences: list[TxnRecord]) -> Decimal:
    """Minimum relative move that counts as a repricing for this series."""
    noise = _typical_variation(occurrences) * PRICE_CHANGE_NOISE_MULTIPLIER
    return max(PRICE_CHANGE_MIN_PCT, noise)


def detect_price_changes(occurrences: list[TxnRecord]) -> list[PriceChange]:
    """Find persistent level shifts in a chronologically sorted series."""
    if len(occurrences) < 2:
        return []

    threshold_pct = price_change_threshold(occurrences)
    changes: list[PriceChange] = []
    level = occurrences[0].amount
    level_txn = occurrences[0]

    for idx in range(1, len(occurrences)):
        current = occurrences[idx]
        delta = current.amount - level
        if level <= 0:
            level, level_txn = current.amount, current
            continue

        pct = abs(delta) / level
        if abs(delta) < PRICE_CHANGE_MIN_ABS or pct < threshold_pct:
            continue

        # A shift is "confirmed" when the next charge stays at the new level.
        confirmed = False
        if idx + 1 < len(occurrences):
            nxt = occurrences[idx + 1].amount
            if current.amount > 0 and abs(nxt - current.amount) / current.amount <= Decimal("0.01"):
                confirmed = True

        evidence = [level_txn.id, current.id]
        if confirmed:
            evidence.append(occurrences[idx + 1].id)

        changes.append(
            PriceChange(
                merchant=current.merchant,
                currency=current.currency,
                previous_amount=level,
                new_amount=current.amount,
                change_amount=delta,
                change_pct=float(pct),
                effective_date=current.posted_date,
                confidence=0.9 if confirmed else 0.55,
                confirmed_by_later_charge=confirmed,
                evidence_transaction_ids=evidence,
            )
        )
        level, level_txn = current.amount, current

    return changes


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------
def reportable_price_changes(series: "RecurringSeries") -> list[PriceChange]:
    """The subset of a series' price changes worth showing a user.

    `detect_price_changes` records every level shift it sees, which is the
    right raw signal. Reporting one as a price change needs more than that:

      * the series has to look like a subscription in the first place,
      * its amount has to be normally steady, and
      * the shift has to be either confirmed by a later charge at the new
        level, or be the most recent charge, where nothing has contradicted
        it yet.
    """
    if series.verdict not in {"likely_recurring", "possible_recurring"}:
        return []
    if series.amount_stability < PRICE_CHANGE_MIN_STABILITY:
        return []
    if not series.occurrences:
        return []

    last_charge_date = series.occurrences[-1].posted_date
    return [
        change
        for change in series.price_changes
        if change.confirmed_by_later_charge or change.effective_date == last_charge_date
    ]


def detect_recurring(
    transactions: list[TxnRecord],
    today: date,
    include_uncertain: bool = True,
) -> list[RecurringSeries]:
    """Group outflows by merchant/currency/account and score each group."""
    groups: dict[tuple[str, str, int], list[TxnRecord]] = {}
    for txn in transactions:
        if txn.direction != "debit":
            continue
        groups.setdefault((txn.merchant, txn.currency, txn.account_id), []).append(txn)

    series_list: list[RecurringSeries] = []
    for (merchant, currency, account_id), items in groups.items():
        if len(items) < MIN_OCCURRENCES:
            continue
        items.sort(key=lambda t: t.posted_date)

        intervals = [
            (items[i].posted_date - items[i - 1].posted_date).days
            for i in range(1, len(items))
        ]
        intervals = [i for i in intervals if i > 0]
        if not intervals:
            continue

        median_interval = float(statistics.median(intervals))
        cadence = classify_cadence(median_interval)
        amounts = [t.amount for t in items]
        confidence, regularity, stability, reasons = _score(
            intervals, amounts, cadence, len(items)
        )
        verdict = verdict_for(confidence, len(items))
        if verdict == "insufficient_evidence" and not include_uncertain:
            continue

        last_seen = items[-1].posted_date
        nominal = CADENCE_BUCKETS.get(cadence, (0, 0, int(median_interval) or 30))[2]
        days_since = (today - last_seen).days
        status = "active" if days_since <= nominal * DORMANT_CYCLE_FACTOR else "dormant"

        next_expected = project_next_date(last_seen, cadence, median_interval)
        while next_expected < today and status == "active":
            next_expected = project_next_date(next_expected, cadence, median_interval)

        series_list.append(
            RecurringSeries(
                merchant=merchant,
                currency=currency,
                account_id=account_id,
                family=items[-1].family,
                occurrences=items,
                cadence=cadence,
                median_interval_days=median_interval,
                interval_regularity=regularity,
                amount_stability=stability,
                typical_amount=Decimal(str(statistics.median([float(a) for a in amounts]))),
                latest_amount=items[-1].amount,
                first_seen=items[0].posted_date,
                last_seen=last_seen,
                confidence=confidence,
                verdict=verdict,
                status=status,
                next_expected_date=next_expected if status == "active" else None,
                price_changes=detect_price_changes(items),
                reasons=reasons,
            )
        )

    series_list.sort(key=lambda s: (-s.confidence, s.merchant))
    return series_list
