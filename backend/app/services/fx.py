"""Currency conversion backed by dated, attributable rates.

Rules this module enforces:
  * A conversion is only produced when a real stored rate supports it.
  * Every result names the rate, its date, its source, and whether the rate is
    simulated demo data.
  * A rate older than the requested date is usable but reported as stale with
    the exact age in days; a missing rate yields `converted=None`, never a
    guess.
  * Cross rates are derived only when both legs exist, and the provenance
    lists both legs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FxRate

PIVOT_CURRENCY = "USD"
STALE_AFTER_DAYS = 7
_CENTS = Decimal("0.01")


def q2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)


@dataclass
class Conversion:
    """Outcome of one currency conversion attempt."""

    amount_original: Decimal
    currency_original: str
    currency_target: str
    converted: Decimal | None = None
    rate: Decimal | None = None
    rate_date: date | None = None
    rate_source: str | None = None
    is_simulated: bool = True
    is_stale: bool = False
    staleness_days: int = 0
    status: str = "ok"  # ok | same_currency | rate_unavailable
    provenance: list[dict] = field(default_factory=list)
    note: str = ""

    @property
    def available(self) -> bool:
        return self.converted is not None

    def to_dict(self) -> dict:
        return {
            "amount_original": float(self.amount_original),
            "currency_original": self.currency_original,
            "currency_target": self.currency_target,
            "amount_converted": float(self.converted) if self.converted is not None else None,
            "rate": float(self.rate) if self.rate is not None else None,
            "rate_date": self.rate_date.isoformat() if self.rate_date else None,
            "rate_source": self.rate_source,
            "is_simulated_rate": self.is_simulated,
            "is_stale": self.is_stale,
            "staleness_days": self.staleness_days,
            "status": self.status,
            "provenance": self.provenance,
            "note": self.note,
        }


class FxService:
    """Dated FX lookups with an in-request memo cache."""

    def __init__(self, db: Session):
        self.db = db
        self._cache: dict[tuple[str, str, date], FxRate | None] = {}

    # -- raw lookups -------------------------------------------------------
    def _lookup(self, base: str, quote: str, on_date: date) -> FxRate | None:
        key = (base, quote, on_date)
        if key in self._cache:
            return self._cache[key]
        row = self.db.execute(
            select(FxRate)
            .where(
                FxRate.base_currency == base,
                FxRate.quote_currency == quote,
                FxRate.as_of_date <= on_date,
            )
            .order_by(FxRate.as_of_date.desc())
            .limit(1)
        ).scalar_one_or_none()
        self._cache[key] = row
        return row

    def _direct_or_inverse(
        self, base: str, quote: str, on_date: date
    ) -> tuple[Decimal, date, str, bool, dict] | None:
        row = self._lookup(base, quote, on_date)
        if row is not None:
            return (
                Decimal(row.rate),
                row.as_of_date,
                row.source,
                row.is_simulated,
                {
                    "pair": f"{base}/{quote}",
                    "rate": float(row.rate),
                    "as_of": row.as_of_date.isoformat(),
                    "source": row.source,
                    "direction": "direct",
                },
            )

        inverse = self._lookup(quote, base, on_date)
        if inverse is not None and Decimal(inverse.rate) != 0:
            rate = Decimal("1") / Decimal(inverse.rate)
            return (
                rate,
                inverse.as_of_date,
                inverse.source,
                inverse.is_simulated,
                {
                    "pair": f"{quote}/{base}",
                    "rate": float(inverse.rate),
                    "as_of": inverse.as_of_date.isoformat(),
                    "source": inverse.source,
                    "direction": "inverted",
                },
            )
        return None

    # -- public API --------------------------------------------------------
    def convert(
        self,
        amount: Decimal | float | int,
        from_currency: str,
        to_currency: str,
        on_date: date,
    ) -> Conversion:
        amount = Decimal(str(amount))
        src = (from_currency or "").upper()
        dst = (to_currency or "").upper()

        if src == dst:
            return Conversion(
                amount_original=amount,
                currency_original=src,
                currency_target=dst,
                converted=q2(amount),
                rate=Decimal("1"),
                rate_date=on_date,
                rate_source="identity",
                is_simulated=False,
                status="same_currency",
                note="No conversion needed.",
            )

        leg = self._direct_or_inverse(src, dst, on_date)
        if leg is not None:
            rate, rate_date, source, simulated, prov = leg
            return self._finish(amount, src, dst, rate, rate_date, source, simulated, [prov], on_date)

        # Derive through the pivot only when both halves genuinely exist.
        first = self._direct_or_inverse(src, PIVOT_CURRENCY, on_date)
        second = self._direct_or_inverse(PIVOT_CURRENCY, dst, on_date)
        if first is not None and second is not None:
            rate = Decimal(first[0]) * Decimal(second[0])
            rate_date = min(first[1], second[1])
            simulated = first[3] or second[3]
            source = f"derived via {PIVOT_CURRENCY}"
            return self._finish(
                amount, src, dst, rate, rate_date, source, simulated,
                [first[4], second[4]], on_date,
                note=f"Cross rate derived from two stored legs through {PIVOT_CURRENCY}.",
            )

        return Conversion(
            amount_original=amount,
            currency_original=src,
            currency_target=dst,
            converted=None,
            status="rate_unavailable",
            note=(
                f"No stored {src}/{dst} rate on or before {on_date.isoformat()}. "
                "Amount left unconverted rather than estimated."
            ),
        )

    def _finish(
        self,
        amount: Decimal,
        src: str,
        dst: str,
        rate: Decimal,
        rate_date: date,
        source: str,
        simulated: bool,
        provenance: list[dict],
        on_date: date,
        note: str = "",
    ) -> Conversion:
        staleness = max((on_date - rate_date).days, 0)
        stale = staleness > STALE_AFTER_DAYS
        notes = [note] if note else []
        if stale:
            notes.append(
                f"Rate is {staleness} days older than the transaction date; "
                "treat the converted figure as an estimate."
            )
        if simulated:
            notes.append("Rate is simulated demo data, not a live market quote.")
        return Conversion(
            amount_original=amount,
            currency_original=src,
            currency_target=dst,
            converted=q2(amount * rate),
            rate=rate,
            rate_date=rate_date,
            rate_source=source,
            is_simulated=simulated,
            is_stale=stale,
            staleness_days=staleness,
            status="ok",
            provenance=provenance,
            note=" ".join(notes),
        )

    def convert_many(
        self, items: list[tuple[Decimal, str, date]], to_currency: str
    ) -> list[Conversion]:
        return [self.convert(a, c, to_currency, d) for a, c, d in items]
