from __future__ import annotations

from datetime import date, timedelta

from app.services.duplicates import analyze_duplicates, find_near_duplicate_transactions
from app.services.recurring import detect_recurring

from .test_recurring import make_series

TODAY = date(2025, 6, 15)


def _series(txns):
    return detect_recurring(txns, today=TODAY)


def test_same_service_on_two_cards_is_flagged_as_a_duplicate():
    txns = make_series("Netflix", ["56.00"] * 6, TODAY - timedelta(days=160), account_id=1)
    txns += make_series(
        "Netflix", ["56.00"] * 6, TODAY - timedelta(days=150), account_id=2, start_id=100
    )
    findings = analyze_duplicates(_series(txns))
    same = [f for f in findings if f.finding_type == "same_service_duplicate"]

    assert len(same) == 1
    assert same[0].verdict == "likely"
    assert same[0].estimated_redundant_monthly is not None
    assert "cancel" in same[0].caveat.lower()


def test_a_single_subscription_is_not_a_duplicate():
    txns = make_series("Netflix", ["56.00"] * 6, TODAY - timedelta(days=160))
    assert [f for f in analyze_duplicates(_series(txns)) if f.finding_type == "same_service_duplicate"] == []


def test_overlapping_family_is_informational_not_an_error():
    txns = make_series("Netflix", ["56.00"] * 6, TODAY - timedelta(days=160), account_id=1)
    txns += make_series(
        "Disney+", ["29.99"] * 6, TODAY - timedelta(days=155), account_id=1, start_id=200
    )
    # The detector only knows the family if the record carries it.
    series = _series(txns)
    for s in series:
        s.family = "video_streaming"

    overlaps = [f for f in analyze_duplicates(series) if f.finding_type == "overlapping_service_family"]
    assert len(overlaps) == 1
    assert overlaps[0].verdict == "informational"
    assert overlaps[0].confidence < 0.7
    assert "deliberate" in overlaps[0].caveat.lower()
    assert set(overlaps[0].merchants) == {"Netflix", "Disney+"}


def test_two_charges_days_apart_are_flagged_as_a_possible_double_charge():
    txns = make_series("Spotify", ["23.99"] * 5, TODAY - timedelta(days=150))
    extra = make_series(
        "Spotify", ["23.99"], txns[2].posted_date + timedelta(days=2), start_id=900
    )
    findings = analyze_duplicates(_series(txns + extra))
    doubles = [f for f in findings if f.finding_type == "double_charge_in_cycle"]

    assert len(doubles) >= 1
    assert doubles[0].verdict == "possible"
    assert doubles[0].estimated_redundant_monthly is None  # no refund promised


def test_dormant_series_do_not_create_duplicate_findings():
    txns = make_series("Netflix", ["56.00"] * 6, TODAY - timedelta(days=400), account_id=1)
    txns += make_series(
        "Netflix", ["56.00"] * 6, TODAY - timedelta(days=395), account_id=2, start_id=100
    )
    assert analyze_duplicates(_series(txns)) == []


def test_raw_transaction_duplicate_scan():
    txns = make_series("Talabat", ["45.00", "45.00"], TODAY - timedelta(days=10), step_days=1)
    hits = find_near_duplicate_transactions(txns)
    assert len(hits) == 1
    assert hits[0]["days_apart"] == 1
