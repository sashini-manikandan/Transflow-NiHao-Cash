from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models import Account, Bill, FxRate, IncomeSource, User
from app.services.forecast import forecast_balance
from app.services.analysis import get_recurring_series


def test_seeded_forecast_warns_about_the_tuition_shortfall(seeded, db, today):
    series = get_recurring_series(db, seeded, today=today)
    result = forecast_balance(db, seeded, series, horizon_days=30, today=today)

    assert result.base_currency == "AED"
    assert result.opening_balance > 0
    assert result.shortfall_detected is True
    assert result.first_shortfall_date is not None
    assert result.largest_shortfall > 0
    assert result.minimum_balance < 0


def test_daily_series_is_contiguous_and_matches_the_horizon(seeded, db, today):
    series = get_recurring_series(db, seeded, today=today)
    result = forecast_balance(db, seeded, series, horizon_days=45, today=today)

    assert len(result.daily) == 46  # today plus 45 days
    assert result.daily[0]["date"] == today.isoformat()
    assert result.daily[-1]["date"] == (today + timedelta(days=45)).isoformat()
    for previous, current in zip(result.daily, result.daily[1:]):
        assert date.fromisoformat(current["date"]) - date.fromisoformat(previous["date"]) == timedelta(days=1)


def test_closing_balance_equals_opening_plus_net_flows(seeded, db, today):
    series = get_recurring_series(db, seeded, today=today)
    result = forecast_balance(db, seeded, series, horizon_days=60, today=today)

    expected = result.opening_balance + result.total_inflow - result.total_outflow
    assert abs(result.closing_balance - expected) < Decimal("0.05")


def test_every_event_declares_its_certainty_and_confidence(seeded, db, today):
    series = get_recurring_series(db, seeded, today=today)
    result = forecast_balance(db, seeded, series, horizon_days=45, today=today)

    assert result.events
    kinds = {e.kind for e in result.events}
    assert {"bill", "recurring_charge", "income"} <= kinds

    for event in result.events:
        payload = event.to_dict()
        assert payload["certainty"] in {"confirmed", "projected", "estimated"}
        assert 0.0 <= payload["confidence"] <= 1.0
        assert payload["direction"] in {"inflow", "outflow"}


def test_confirmed_bills_outrank_projected_charges_in_certainty(seeded, db, today):
    series = get_recurring_series(db, seeded, today=today)
    result = forecast_balance(db, seeded, series, horizon_days=45, today=today)

    bills = [e for e in result.events if e.kind == "bill"]
    projected = [e for e in result.events if e.kind == "recurring_charge"]
    assert all(e.certainty == "confirmed" for e in bills)
    assert all(e.certainty == "projected" for e in projected)


def test_forecast_lists_its_assumptions(seeded, db, today):
    series = get_recurring_series(db, seeded, today=today)
    result = forecast_balance(db, seeded, series, horizon_days=30, today=today)
    joined = " ".join(result.assumptions).lower()
    assert "synthetic" in joined
    assert "assume" in joined


def test_turning_off_projections_leaves_only_confirmed_items(seeded, db, today):
    series = get_recurring_series(db, seeded, today=today)
    with_proj = forecast_balance(db, seeded, series, horizon_days=30, today=today)
    without = forecast_balance(
        db, seeded, series, horizon_days=30, today=today, include_projected_recurring=False
    )
    assert without.total_outflow < with_proj.total_outflow
    assert not any(e.kind == "recurring_charge" for e in without.events)


# --------------------------------------------------------------------------
# isolated scenarios
# --------------------------------------------------------------------------
def _minimal_user(db, balance: str, currency: str = "AED") -> User:
    user = User(email="t@example.com", full_name="T", base_currency="AED")
    db.add(user)
    db.flush()
    db.add(
        Account(
            user_id=user.id, name="Main", institution="Demo", currency=currency,
            current_balance=Decimal(balance),
        )
    )
    db.flush()
    return user


def test_a_bill_we_cannot_convert_is_excluded_not_guessed(db, today):
    user = _minimal_user(db, "1000.00")
    db.add(
        Bill(
            user_id=user.id, name="Istanbul deposit", due_date=today + timedelta(days=5),
            amount=Decimal("4250.00"), currency="TRY", status="upcoming",
        )
    )
    db.flush()

    result = forecast_balance(db, user, [], horizon_days=30, today=today)

    assert result.closing_balance == Decimal("1000.00")  # untouched
    assert len(result.excluded) == 1
    assert result.excluded[0]["currency"] == "TRY"
    assert "No stored" in result.excluded[0]["reason"]
    event = next(e for e in result.events if e.label == "Istanbul deposit")
    assert event.amount_base is None
    assert event.conversion_status == "rate_unavailable"


def test_income_arriving_after_a_bill_still_shows_the_dip(db, today):
    user = _minimal_user(db, "500.00")
    db.add(
        Bill(
            user_id=user.id, name="Rent", due_date=today + timedelta(days=5),
            amount=Decimal("2000.00"), currency="AED", status="upcoming",
        )
    )
    db.add(
        IncomeSource(
            user_id=user.id, name="Stipend", amount=Decimal("4000.00"), currency="AED",
            cadence="monthly", day_of_month=28,
            next_expected_date=today + timedelta(days=12),
        )
    )
    db.flush()

    result = forecast_balance(db, user, [], horizon_days=30, today=today)

    assert result.shortfall_detected is True
    assert result.first_shortfall_date == today + timedelta(days=5)
    assert result.largest_shortfall == Decimal("1500.00")
    assert result.closing_balance == Decimal("2500.00")  # recovers after payday


def test_a_comfortable_balance_reports_no_shortfall(db, today):
    user = _minimal_user(db, "9000.00")
    db.add(
        Bill(
            user_id=user.id, name="Small bill", due_date=today + timedelta(days=3),
            amount=Decimal("120.00"), currency="AED", status="upcoming",
        )
    )
    db.flush()

    result = forecast_balance(db, user, [], horizon_days=30, today=today)
    assert result.shortfall_detected is False
    assert result.first_shortfall_date is None
    assert result.largest_shortfall is None
    assert result.minimum_balance == Decimal("8880.00")


def test_foreign_account_balance_is_converted_into_the_opening_position(db, today):
    user = _minimal_user(db, "0.00")
    db.add(
        Account(
            user_id=user.id, name="USD card", institution="Demo", currency="USD",
            current_balance=Decimal("100.00"),
        )
    )
    db.add(
        FxRate(
            base_currency="USD", quote_currency="AED", rate=Decimal("3.6725"),
            as_of_date=today,
        )
    )
    db.flush()

    result = forecast_balance(db, user, [], horizon_days=7, today=today)
    assert result.opening_balance == Decimal("367.25")
    assert len(result.opening_balance_breakdown) == 2


def test_already_paid_bills_never_enter_the_projection(db, today):
    user = _minimal_user(db, "1000.00")
    db.add(
        Bill(
            user_id=user.id, name="Paid already", due_date=today + timedelta(days=2),
            amount=Decimal("300.00"), currency="AED", status="paid",
        )
    )
    db.flush()

    result = forecast_balance(db, user, [], horizon_days=10, today=today)
    assert result.closing_balance == Decimal("1000.00")
    assert result.events == []
