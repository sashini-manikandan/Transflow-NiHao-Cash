"""Detector behaviour on hand-built series, independent of the database."""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from app.services.recurring import (
    TxnRecord,
    classify_cadence,
    detect_price_changes,
    detect_recurring,
    price_change_threshold,
    reportable_price_changes,
)

TODAY = date(2025, 6, 15)


def make_series(
    merchant: str,
    amounts: list[str],
    start: date,
    step_days: int = 30,
    account_id: int = 1,
    currency: str = "AED",
    start_id: int = 1,
) -> list[TxnRecord]:
    return [
        TxnRecord(
            id=start_id + i,
            posted_date=start + timedelta(days=step_days * i),
            amount=Decimal(a),
            currency=currency,
            merchant=merchant,
            account_id=account_id,
            description=f"{merchant} charge",
        )
        for i, a in enumerate(amounts)
    ]


def test_clean_monthly_series_is_likely_recurring():
    txns = make_series("Netflix", ["56.00"] * 8, TODAY - timedelta(days=210))
    (series,) = detect_recurring(txns, today=TODAY)

    assert series.cadence == "monthly"
    assert series.verdict == "likely_recurring"
    assert series.confidence >= 0.85
    assert series.status == "active"
    assert series.next_expected_date > TODAY
    assert len(series.occurrences) == 8


def test_two_occurrences_are_at_best_possible_never_likely():
    txns = make_series("Notion", ["8.00", "8.00"], TODAY - timedelta(days=30))
    (series,) = detect_recurring(txns, today=TODAY)

    assert series.verdict != "likely_recurring"
    assert "short history" in " ".join(series.reasons).lower()


def test_single_transaction_produces_no_series():
    txns = make_series("Carrefour", ["120.00"], TODAY - timedelta(days=10))
    assert detect_recurring(txns, today=TODAY) == []


def test_irregular_spending_is_not_reported_as_recurring():
    rng = random.Random(7)
    txns = [
        TxnRecord(
            id=i,
            posted_date=TODAY - timedelta(days=rng.randint(1, 300)),
            amount=Decimal(str(round(rng.uniform(20, 400), 2))),
            currency="AED",
            merchant="Carrefour",
            account_id=1,
        )
        for i in range(1, 16)
    ]
    series = detect_recurring(txns, today=TODAY)
    assert all(s.verdict == "insufficient_evidence" for s in series)


def test_annual_cadence_is_recognised():
    txns = make_series(
        "Duolingo", ["83.99", "83.99"], date(2023, 6, 6), step_days=365, currency="USD"
    )
    (series,) = detect_recurring(txns, today=TODAY)
    assert series.cadence == "annual"


def test_weekly_and_quarterly_buckets():
    assert classify_cadence(7) == "weekly"
    assert classify_cadence(14) == "biweekly"
    assert classify_cadence(30.5) == "monthly"
    assert classify_cadence(91) == "quarterly"
    assert classify_cadence(365) == "annual"
    assert classify_cadence(47) == "irregular"


def test_lapsed_series_becomes_dormant_with_no_next_date():
    txns = make_series("Coursera", ["49.00"] * 5, TODAY - timedelta(days=360))
    (series,) = detect_recurring(txns, today=TODAY)
    assert series.status == "dormant"
    assert series.next_expected_date is None


def test_variable_amounts_lower_stability_but_regular_timing_still_detected():
    txns = make_series(
        "du Telecom", ["110.00", "138.00", "121.00", "145.00", "118.00", "133.00"],
        TODAY - timedelta(days=150),
    )
    (series,) = detect_recurring(txns, today=TODAY)
    assert series.cadence == "monthly"
    assert series.amount_stability < 0.7
    assert series.verdict in {"likely_recurring", "possible_recurring"}


def test_price_increase_confirmed_by_later_charge():
    txns = make_series(
        "Netflix", ["56.00", "56.00", "56.00", "61.75", "61.75", "61.75"],
        TODAY - timedelta(days=150),
    )
    changes = detect_price_changes(txns)

    assert len(changes) == 1
    change = changes[0]
    assert change.previous_amount == Decimal("56.00")
    assert change.new_amount == Decimal("61.75")
    assert change.change_amount == Decimal("5.75")
    assert change.confirmed_by_later_charge is True
    assert change.confidence >= 0.9
    assert round(change.change_pct, 4) == round(5.75 / 56.00, 4)


def test_unconfirmed_price_change_has_lower_confidence():
    txns = make_series("Adobe", ["19.99", "19.99", "22.99"], TODAY - timedelta(days=60))
    (change,) = detect_price_changes(txns)
    assert change.confirmed_by_later_charge is False
    assert change.confidence < 0.7


def test_rounding_noise_is_not_a_price_change():
    txns = make_series("Spotify", ["23.99", "24.00", "23.99", "24.01"], TODAY - timedelta(days=120))
    assert detect_price_changes(txns) == []


def test_a_steady_series_keeps_the_sensitive_default_threshold():
    steady = make_series("Netflix", ["56.00"] * 8, TODAY - timedelta(days=240))
    assert price_change_threshold(steady) == Decimal("0.01")


def test_a_wobbly_series_demands_a_much_larger_move():
    """A metered bill varies every month, so small moves are not repricings."""
    wobbly = make_series(
        "DEWA",
        ["210.00", "248.00", "191.00", "233.00", "205.00", "262.00", "198.00", "241.00"],
        TODAY - timedelta(days=240),
    )
    assert price_change_threshold(wobbly) > Decimal("0.15")


def test_routine_variation_in_a_metered_bill_is_not_a_price_change():
    wobbly = make_series(
        "DEWA",
        ["210.00", "248.00", "191.00", "233.00", "205.00", "262.00", "198.00", "241.00"],
        TODAY - timedelta(days=240),
    )
    assert detect_price_changes(wobbly) == []


def test_a_genuine_step_is_still_caught_inside_a_noisy_series():
    noisy_then_stepped = make_series(
        "Mobile plan",
        ["100.00", "106.00", "97.00", "103.00", "99.00", "104.00",
         "180.00", "182.00", "179.00"],
        TODAY - timedelta(days=270),
    )
    changes = detect_price_changes(noisy_then_stepped)
    assert len(changes) == 1
    assert changes[0].new_amount == Decimal("180.00")


def test_price_decrease_is_reported_with_direction():
    txns = make_series("GymNation", ["199.00", "199.00", "149.00", "149.00"], TODAY - timedelta(days=120))
    (change,) = detect_price_changes(txns)
    assert change.change_amount < 0
    assert change.to_dict()["direction"] == "decrease"


def test_credits_are_ignored_by_the_detector():
    txns = [
        TxnRecord(
            id=i,
            posted_date=TODAY - timedelta(days=30 * i),
            amount=Decimal("4000.00"),
            currency="AED",
            merchant="NYUAD Stipend",
            account_id=1,
            direction="credit",
        )
        for i in range(1, 6)
    ]
    assert detect_recurring(txns, today=TODAY) == []


def test_same_merchant_on_two_accounts_yields_two_series():
    txns = make_series("Netflix", ["56.00"] * 6, TODAY - timedelta(days=160), account_id=1)
    txns += make_series(
        "Netflix", ["15.49"] * 6, TODAY - timedelta(days=150),
        account_id=2, currency="USD", start_id=100,
    )
    series = detect_recurring(txns, today=TODAY)
    assert len(series) == 2
    assert {s.account_id for s in series} == {1, 2}


def test_irregular_everyday_spending_reports_no_price_changes():
    """Groceries land on random days for random amounts; no shift means anything."""
    rng = random.Random(11)
    day = 300
    txns = []
    for i in range(1, 16):
        day -= rng.randint(4, 32)
        txns.append(
            TxnRecord(
                id=i,
                posted_date=TODAY - timedelta(days=day),
                amount=Decimal(str(round(rng.uniform(20, 400), 2))),
                currency="AED",
                merchant="Carrefour",
                account_id=1,
            )
        )

    (series,) = detect_recurring(txns, today=TODAY)
    assert series.verdict == "insufficient_evidence"
    assert reportable_price_changes(series) == []


def test_an_unconfirmed_change_is_only_reportable_at_the_latest_charge():
    txns = make_series(
        "Netflix", ["56.00", "56.00", "56.00", "56.00", "61.75"],
        TODAY - timedelta(days=120),
    )
    (series,) = detect_recurring(txns, today=TODAY)
    reportable = reportable_price_changes(series)

    assert len(reportable) == 1
    assert reportable[0].confirmed_by_later_charge is False
    assert reportable[0].effective_date == series.last_seen


def test_monthly_equivalent_normalises_annual_plans():
    txns = make_series(
        "Duolingo", ["120.00", "120.00"], date(2023, 6, 6), step_days=365, currency="USD"
    )
    (series,) = detect_recurring(txns, today=TODAY)
    assert 9 < float(series.monthly_equivalent) < 11
