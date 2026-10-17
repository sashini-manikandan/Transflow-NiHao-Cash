"""End-to-end checks that the seeded demo dataset actually exercises every
analysis path the product claims to support.
"""

from __future__ import annotations

from app.services.analysis import (
    analyze_currency_costs,
    analyze_subscriptions,
    get_recurring_series,
    get_savings_options,
    get_upcoming_bills,
)


def test_seed_creates_a_single_demo_user_and_is_idempotent(db, today):
    from app.models import Transaction, User
    from app.seed.seed_data import seed_if_empty

    assert seed_if_empty(db, email="amina@demo.billwise.ai", today=today) is True
    first_count = db.query(Transaction).count()
    assert seed_if_empty(db, email="amina@demo.billwise.ai", today=today) is False

    assert db.query(User).count() == 1
    assert db.query(Transaction).count() == first_count
    assert first_count > 200


def test_all_seeded_data_is_marked_synthetic(seeded, db):
    from app.models import Account, FxRate, Transaction

    assert all(t.is_synthetic for t in db.query(Transaction).all())
    assert all(a.is_synthetic for a in db.query(Account).all())
    assert all(r.is_simulated for r in db.query(FxRate).all())


def test_known_subscriptions_are_detected_with_high_confidence(seeded, db, today):
    result = analyze_subscriptions(db, seeded, today=today)
    merchants = {s["merchant"]: s for s in result["subscriptions"]}

    for expected in ["Netflix", "Spotify", "ChatGPT Plus", "Adobe Creative Cloud", "GymNation"]:
        assert expected in merchants, f"{expected} not detected"

    assert merchants["Spotify"]["verdict"] == "likely_recurring"
    assert merchants["Spotify"]["cadence"] == "monthly"
    assert result["summary"]["likely_count"] >= 8


def test_noisy_everyday_spending_is_not_sold_as_a_subscription(seeded, db, today):
    series = get_recurring_series(db, seeded, today=today)
    noisy = {"Carrefour Marina Mall", "Talabat", "Starbucks Campus", "Careem"}
    for s in series:
        if s.merchant in noisy:
            assert s.verdict == "insufficient_evidence", (
                f"{s.merchant} was wrongly scored {s.confidence}"
            )


def test_every_subscription_carries_evidence_and_a_confidence_score(seeded, db, today):
    result = analyze_subscriptions(db, seeded, today=today)
    for sub in result["subscriptions"]:
        assert sub["evidence"], f"{sub['merchant']} has no evidence"
        assert 0.0 <= sub["confidence"] <= 1.0
        assert sub["verdict"] in {
            "likely_recurring", "possible_recurring", "insufficient_evidence",
        }
        assert sub["reasons"]


def test_netflix_billed_on_two_cards_surfaces_as_a_duplicate(seeded, db, today):
    result = analyze_subscriptions(db, seeded, today=today)
    same = [
        f for f in result["duplicate_findings"]
        if f["finding_type"] == "same_service_duplicate"
    ]
    assert any("Netflix" in f["merchants"] for f in same)


def test_streaming_and_music_overlaps_are_reported(seeded, db, today):
    result = analyze_subscriptions(db, seeded, today=today)
    families = {
        tuple(sorted(f["merchants"]))
        for f in result["duplicate_findings"]
        if f["finding_type"] == "overlapping_service_family"
    }
    flat = {m for group in families for m in group}
    assert {"Netflix", "Disney+"} <= flat
    assert {"Spotify", "Apple Music"} <= flat


def test_seeded_price_rises_are_detected_with_the_right_numbers(seeded, db, today):
    result = analyze_subscriptions(db, seeded, today=today)
    by_merchant = {c["merchant"]: c for c in result["price_changes"]}

    assert "Netflix" in by_merchant
    netflix = by_merchant["Netflix"]
    assert netflix["previous_amount"] == 56.00
    assert netflix["new_amount"] == 61.75
    assert netflix["direction"] == "increase"
    assert netflix["confirmed_by_later_charge"] is True

    assert "Adobe Creative Cloud" in by_merchant
    assert by_merchant["Adobe Creative Cloud"]["new_amount"] == 22.99


NOISY_MERCHANTS = {
    "Carrefour Marina Mall",
    "Lulu Hypermarket",
    "Starbucks Campus",
    "Talabat",
    "Careem",
    "Uber Trip Help Uber",
    "Bookstore Campus",
}


def test_variable_everyday_spending_never_reports_a_price_change(seeded, db, today):
    """Groceries and taxi fares change every time; that is not a price rise."""
    result = analyze_subscriptions(db, seeded, today=today)
    reported = {c["merchant"] for c in result["price_changes"]}
    assert not (reported & NOISY_MERCHANTS), f"noise reported as price changes: {reported}"


def test_a_steady_subscription_with_small_jitter_reports_no_repricing(seeded, db, today):
    """The Ghana airtime top-up wobbles a few percent monthly but never reprices."""
    result = analyze_subscriptions(db, seeded, today=today)
    reported = {c["merchant"] for c in result["price_changes"]}
    assert not {m for m in reported if "Mtn" in m or "MTN" in m}


def test_the_only_reported_repricings_are_the_two_genuine_ones(seeded, db, today):
    """Netflix and Adobe are the only seeded step changes; nothing else qualifies."""
    result = analyze_subscriptions(db, seeded, today=today)
    assert {c["merchant"] for c in result["price_changes"]} == {
        "Netflix",
        "Adobe Creative Cloud",
    }


def test_usage_based_utility_bills_are_not_reported_as_repricings(seeded, db, today):
    """A metered bill that moves 20% a month is variable, not repriced."""
    result = analyze_subscriptions(db, seeded, today=today)
    assert "DEWA Utilities" not in {c["merchant"] for c in result["price_changes"]}


def test_price_changes_are_either_confirmed_or_the_most_recent_charge(seeded, db, today):
    series = {s.merchant: s for s in get_recurring_series(db, seeded, today=today)}
    result = analyze_subscriptions(db, seeded, today=today)

    for change in result["price_changes"]:
        source = series[change["merchant"]]
        assert (
            change["confirmed_by_later_charge"]
            or change["effective_date"] == source.last_seen.isoformat()
        )


def test_the_savings_list_stays_short_and_actionable(seeded, db, today):
    """A list of 70 'savings' would be noise, not a recommendation."""
    options = get_savings_options(db, seeded, today=today)
    assert 0 < len(options) <= 15
    assert not ({o.action_target for o in options} & NOISY_MERCHANTS)


def test_cancelled_course_subscription_reads_as_dormant(seeded, db, today):
    series = {s.merchant: s for s in get_recurring_series(db, seeded, today=today)}
    assert series["Coursera"].status == "dormant"
    assert series["Coursera"].next_expected_date is None


def test_subscription_totals_are_reported_in_the_base_currency(seeded, db, today):
    result = analyze_subscriptions(db, seeded, today=today)
    assert result["base_currency"] == "AED"
    assert result["summary"]["estimated_monthly_total_base"] > 0
    for sub in result["subscriptions"]:
        if sub["status"] == "active" and sub["currency"] != "AED":
            assert sub["monthly_equivalent_base"] is not None
            assert sub["conversion"]["rate_date"] is not None


def test_upcoming_bills_are_converted_and_ordered(seeded, db, today):
    result = get_upcoming_bills(db, seeded, days_ahead=45, today=today)
    assert result["count"] >= 5
    dates = [b["due_date"] for b in result["bills"]]
    assert dates == sorted(dates)
    assert result["total_due_base"] > 0

    ghs_bill = next(b for b in result["bills"] if b["currency"] == "GHS")
    assert ghs_bill["amount_base"] is not None
    assert ghs_bill["conversion"]["is_simulated_rate"] is True


def test_paid_bills_are_excluded_by_default(seeded, db, today):
    result = get_upcoming_bills(db, seeded, days_ahead=60, today=today)
    assert all(b["status"] != "paid" for b in result["bills"])


def test_currency_analysis_separates_what_it_cannot_convert(seeded, db, today):
    result = analyze_currency_costs(db, seeded, months=6, today=today)

    assert result["summary"]["currencies_used"] >= 3
    assert result["summary"]["foreign_currency_spend_base"] > 0
    assert result["summary"]["disclosed_fees_base"] > 0

    # The seeded Turkish lira hotel charge has no stored TRY rate.
    assert result["summary"]["unconvertible_transaction_count"] >= 1
    assert any(t["currency"] == "TRY" for t in result["unconvertible_transactions"])
    assert all("No stored" in t["reason"] for t in result["unconvertible_transactions"])


def test_currency_rows_cite_the_rate_they_used(seeded, db, today):
    result = analyze_currency_costs(db, seeded, months=6, today=today)
    for row in result["by_currency"]:
        if row["is_base_currency"] or row["converted_count"] == 0:
            continue
        assert row["latest_rate"] is not None
        assert row["rate_date"] is not None
        assert row["is_simulated_rate"] is True


def test_savings_options_are_ranked_and_always_explain_their_basis(seeded, db, today):
    options = get_savings_options(db, seeded, today=today)
    assert options

    categories = {o.category for o in options}
    assert "duplicate_subscription" in categories
    assert "price_increase" in categories

    for option in options:
        payload = option.to_dict()
        assert payload["impact_basis"]
        assert payload["caveats"]
        assert 0.0 <= payload["confidence"] <= 1.0
        if payload["estimated_monthly_saving_base"] is not None:
            assert payload["estimated_monthly_saving_base"] > 0
            assert payload["currency"] == "AED"
