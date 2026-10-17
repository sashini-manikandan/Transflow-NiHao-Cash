"""Simulated remittance route comparison: traditional rails vs stablecoin.

All figures are demo estimates for the hackathon bonus track. Nothing here
initiates a real transfer, touches a wallet, or quotes a live exchange.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from ..models import User
from .fx import FxService, q2

# Demo fee schedules — labelled simulated in every response.
WIRE_FEE_FLAT = Decimal("18.50")
WIRE_FEE_PCT = Decimal("0.012")  # 1.2% of send amount
STABLECOIN_FEE_FLAT = Decimal("2.50")  # network + on/off-ramp demo fee
STABLECOIN_FEE_PCT = Decimal("0.002")  # 0.2%
STABLECOIN_ASSET = "USDC"


@dataclass
class RouteQuote:
    route: str
    label: str
    fee_base: Decimal
    amount_received_dest: Decimal | None
    destination_currency: str
    total_cost_base: Decimal | None
    eta_business_days: str
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "route": self.route,
            "label": self.label,
            "fee_base": float(self.fee_base),
            "amount_received_dest": (
                float(self.amount_received_dest)
                if self.amount_received_dest is not None
                else None
            ),
            "destination_currency": self.destination_currency,
            "total_cost_base": (
                float(self.total_cost_base) if self.total_cost_base is not None else None
            ),
            "eta_business_days": self.eta_business_days,
            "notes": self.notes,
        }


def simulate_remittance(
    db: Session,
    user: User,
    *,
    amount: Decimal,
    source_currency: str | None = None,
    destination_currency: str = "GHS",
    today: date | None = None,
) -> dict:
    """Compare a traditional remittance rail with a USDC simulation.

    The send amount is in the user's reporting (or stated) currency. Destination
    payout uses dated demo FX rates when available; otherwise that leg is marked
    unavailable rather than invented.
    """
    today = today or date.today()
    source = (source_currency or user.base_currency).upper()
    dest = destination_currency.upper()
    amount = q2(amount)
    fx = FxService(db)

    wire_fee = q2(WIRE_FEE_FLAT + amount * WIRE_FEE_PCT)
    stable_fee = q2(STABLECOIN_FEE_FLAT + amount * STABLECOIN_FEE_PCT)

    # Amount that actually leaves after fees (in source currency).
    wire_net = amount  # fee charged on top in this demo model
    stable_net = amount

    wire_received = _convert_payout(fx, wire_net, source, dest, today)
    # Stablecoin path: convert source → USD (USDC peg), then USD → dest.
    # Peg is assumed 1 USDC = 1 USD for the simulation only.
    to_usd = fx.convert(stable_net, source, "USD", today)
    if to_usd.available and to_usd.converted is not None:
        usdc_amount = q2(to_usd.converted)
        stable_received = _convert_payout(fx, usdc_amount, "USD", dest, today)
        stable_peg_note = (
            f"Assumes 1 {STABLECOIN_ASSET} = 1 USD for this simulation only."
        )
    else:
        usdc_amount = None
        stable_received = None
        stable_peg_note = (
            to_usd.note or "Could not convert send amount to USD for the USDC leg."
        )

    wire_route = RouteQuote(
        route="traditional_wire",
        label="Traditional remittance (Wise-style demo)",
        fee_base=_fee_in_base(fx, wire_fee, source, user.base_currency, today),
        amount_received_dest=wire_received,
        destination_currency=dest,
        total_cost_base=_fee_in_base(
            fx, amount + wire_fee, source, user.base_currency, today
        ),
        eta_business_days="1–3",
        notes=[
            "Fee schedule is simulated demo data, not a live provider quote.",
            f"Flat {WIRE_FEE_FLAT} + {WIRE_FEE_PCT * 100:.1f}% of send amount.",
        ],
    )

    stable_route = RouteQuote(
        route="stablecoin_usdc",
        label=f"Stablecoin remittance ({STABLECOIN_ASSET} simulation)",
        fee_base=_fee_in_base(fx, stable_fee, source, user.base_currency, today),
        amount_received_dest=stable_received,
        destination_currency=dest,
        total_cost_base=_fee_in_base(
            fx, amount + stable_fee, source, user.base_currency, today
        ),
        eta_business_days="same day – 1",
        notes=[
            "SIMULATION ONLY — no wallet, chain, or on-ramp is connected.",
            stable_peg_note,
            f"Demo fee: flat {STABLECOIN_FEE_FLAT} + {STABLECOIN_FEE_PCT * 100:.1f}%.",
            "Payout to local currency still needs an off-ramp in the real world.",
        ],
    )

    savings = None
    if (
        wire_route.fee_base is not None
        and stable_route.fee_base is not None
    ):
        savings = float(q2(Decimal(str(wire_route.fee_base)) - Decimal(str(stable_route.fee_base))))

    recommendation = "compare_both"
    if savings is not None and savings > 0:
        recommendation = "stablecoin_sim_cheaper_on_fees"
    elif savings is not None and savings < 0:
        recommendation = "traditional_cheaper_on_fees"

    return {
        "as_of": today.isoformat(),
        "simulation": True,
        "disclaimer": (
            "Both routes are sandbox simulations for demo scoring. Nothing is "
            "sent, no USDC is moved, and fees are not live market quotes."
        ),
        "send": {
            "amount": float(amount),
            "currency": source,
            "destination_currency": dest,
        },
        "routes": [wire_route.to_dict(), stable_route.to_dict()],
        "fee_savings_base_if_stablecoin": savings,
        "reporting_currency": user.base_currency,
        "recommendation": recommendation,
        "requires_user_authorization": True,
        "executable": False,
    }


def _convert_payout(
    fx: FxService, amount: Decimal, source: str, dest: str, today: date
) -> Decimal | None:
    if source == dest:
        return q2(amount)
    conv = fx.convert(amount, source, dest, today)
    if not conv.available or conv.converted is None:
        return None
    return q2(conv.converted)


def _fee_in_base(
    fx: FxService, amount: Decimal, currency: str, base: str, today: date
) -> Decimal:
    if currency == base:
        return q2(amount)
    conv = fx.convert(amount, currency, base, today)
    if conv.available and conv.converted is not None:
        return q2(conv.converted)
    return q2(amount)
