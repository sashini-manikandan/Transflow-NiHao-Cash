"""FX conversion must be traceable, dated, and honest about gaps."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import FxRate
from app.services.fx import FxService

ON = date(2025, 6, 15)


@pytest.fixture()
def rates(db):
    db.add_all(
        [
            FxRate(
                base_currency="USD", quote_currency="AED", rate=Decimal("3.6725"),
                as_of_date=ON, source="simulated-demo-table", is_simulated=True,
            ),
            FxRate(
                base_currency="USD", quote_currency="EUR", rate=Decimal("0.8600"),
                as_of_date=ON, source="simulated-demo-table", is_simulated=True,
            ),
            FxRate(
                base_currency="USD", quote_currency="GHS", rate=Decimal("15.40"),
                as_of_date=ON - timedelta(days=40), source="simulated-demo-table",
                is_simulated=True,
            ),
        ]
    )
    db.flush()
    return FxService(db)


def test_same_currency_is_identity_without_touching_rate_table(rates):
    result = rates.convert(Decimal("100"), "AED", "AED", ON)
    assert result.status == "same_currency"
    assert result.converted == Decimal("100.00")
    assert result.is_simulated is False


def test_direct_rate_conversion_reports_its_provenance(rates):
    result = rates.convert(Decimal("20.00"), "USD", "AED", ON)
    assert result.converted == Decimal("73.45")
    assert result.rate_date == ON
    assert result.rate_source == "simulated-demo-table"
    assert result.is_simulated is True
    assert result.provenance[0]["direction"] == "direct"
    assert "simulated" in result.note.lower()


def test_inverse_rate_is_used_when_only_the_reverse_pair_exists(rates):
    result = rates.convert(Decimal("36.725"), "AED", "USD", ON)
    assert result.converted == Decimal("10.00")
    assert result.provenance[0]["direction"] == "inverted"


def test_cross_rate_is_derived_from_two_stored_legs(rates):
    result = rates.convert(Decimal("100"), "EUR", "AED", ON)
    assert result.available
    assert len(result.provenance) == 2
    assert "derived via USD" == result.rate_source
    # 100 EUR -> USD (1/0.86) -> AED (x3.6725)
    assert result.converted == pytest.approx(Decimal("427.03"), abs=Decimal("0.02"))


def test_missing_rate_returns_no_amount_and_explains_why(rates):
    result = rates.convert(Decimal("4250.00"), "TRY", "AED", ON)
    assert result.converted is None
    assert result.available is False
    assert result.status == "rate_unavailable"
    assert "TRY/AED" in result.note
    assert result.to_dict()["amount_converted"] is None


def test_future_dated_rates_are_never_used(db):
    db.add(
        FxRate(
            base_currency="USD", quote_currency="AED", rate=Decimal("3.6725"),
            as_of_date=ON + timedelta(days=5), source="simulated-demo-table",
        )
    )
    db.flush()
    result = FxService(db).convert(Decimal("10"), "USD", "AED", ON)
    assert result.status == "rate_unavailable"


def test_stale_rate_is_used_but_flagged_with_its_age(rates):
    result = rates.convert(Decimal("1000"), "GHS", "AED", ON)
    assert result.available
    assert result.is_stale is True
    assert result.staleness_days == 40
    assert "40 days older" in result.note


def test_most_recent_rate_on_or_before_the_date_wins(db):
    db.add_all(
        [
            FxRate(base_currency="USD", quote_currency="GHS", rate=Decimal("11.80"),
                   as_of_date=ON - timedelta(days=200)),
            FxRate(base_currency="USD", quote_currency="GHS", rate=Decimal("15.40"),
                   as_of_date=ON - timedelta(days=2)),
        ]
    )
    db.flush()
    result = FxService(db).convert(Decimal("1"), "USD", "GHS", ON)
    assert result.rate == Decimal("15.40")
    assert result.is_stale is False
