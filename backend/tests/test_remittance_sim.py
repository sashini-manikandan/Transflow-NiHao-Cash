"""Stablecoin vs traditional remittance simulation."""

from decimal import Decimal

from app.services.remittance_sim import simulate_remittance


def test_remittance_sim_returns_both_routes_and_never_executes(seeded, db, today):
    result = simulate_remittance(
        db, seeded, amount=Decimal("1100"), destination_currency="GHS", today=today
    )

    assert result["simulation"] is True
    assert result["executable"] is False
    assert result["requires_user_authorization"] is True
    routes = {row["route"] for row in result["routes"]}
    assert routes == {"traditional_wire", "stablecoin_usdc"}
    for row in result["routes"]:
        assert row["fee_base"] > 0
        assert "SIMULATION" in " ".join(row["notes"]).upper() or "simulated" in " ".join(
            row["notes"]
        ).lower() or "demo" in " ".join(row["notes"]).lower()


def test_stablecoin_route_has_lower_demo_fee_than_wire(seeded, db, today):
    result = simulate_remittance(
        db, seeded, amount=Decimal("1100"), destination_currency="GHS", today=today
    )
    by_route = {row["route"]: row for row in result["routes"]}
    assert by_route["stablecoin_usdc"]["fee_base"] < by_route["traditional_wire"]["fee_base"]
    assert result["fee_savings_base_if_stablecoin"] > 0


def test_remittance_sim_api(client):
    body = client.get(
        "/api/currency/remittance-sim",
        params={"amount": 1100, "destination_currency": "GHS"},
    ).json()
    assert body["executable"] is False
    assert len(body["routes"]) == 2
    assert "sandbox" in body["disclaimer"].lower() or "simulation" in body["disclaimer"].lower()
