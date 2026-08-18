"""Portfolio endpoints and the trade-ledger replay.

Holdings are derived from the trade ledger on every read, so these tests pin the
arithmetic that derivation performs: weighted-average cost basis, fees on both
legs, realised profit on partial and full exits, and portfolio weights.

Every expected figure below is computed by hand in a comment. A test that just
records whatever the code currently returns would pass through a rounding bug
unchanged.

Prices come from the pinned seeded provider, whose generated series always ends
exactly on the configured ``base_price`` - so LUCK's latest close is 892.00 in
every run.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.api

#: LUCK's final generated close. Pinned by the provider's endpoint anchoring.
LUCK_CLOSE = Decimal("892.00")


def buy(
    client: TestClient,
    api: str,
    symbol: str = "LUCK",
    *,
    quantity: str = "100",
    price: str = "800",
    fees: str = "0",
    **extra: object,
) -> dict:
    response = client.post(
        f"{api}/portfolio/trades",
        json={
            "symbol": symbol,
            "side": "buy",
            "quantity": quantity,
            "price": price,
            "fees": fees,
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def sell(
    client: TestClient,
    api: str,
    symbol: str = "LUCK",
    *,
    quantity: str = "100",
    price: str = "900",
    fees: str = "0",
) -> dict:
    response = client.post(
        f"{api}/portfolio/trades",
        json={
            "symbol": symbol,
            "side": "sell",
            "quantity": quantity,
            "price": price,
            "fees": fees,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def portfolio(client: TestClient, api: str) -> dict:
    response = client.get(f"{api}/portfolio")
    assert response.status_code == 200, response.text
    return response.json()


def holding(body: dict, symbol: str) -> dict:
    return next(item for item in body["holdings"] if item["symbol"] == symbol)


def set_profile(client: TestClient, api: str, **overrides: object) -> None:
    payload = {
        "time_horizon": "long_term",
        "risk_tolerance": "moderate",
        "investable_capital": "1000000",
        "max_position_pct": "15",
        "max_sector_pct": "35",
    } | overrides
    response = client.put(f"{api}/profile", json=payload)
    assert response.status_code == 200, response.text


class TestEmptyPortfolio:
    def test_an_untraded_portfolio_is_empty_not_an_error(
        self, seeded_client: TestClient, api: str
    ) -> None:
        body = portfolio(seeded_client, api)

        assert body["holdings"] == []
        assert body["sector_allocations"] == []
        assert body["concentration_warnings"] == []
        assert body["valued_at"] is None
        assert body["summary"]["holdings_count"] == 0
        assert Decimal(body["summary"]["total_market_value"]) == Decimal("0.00")
        assert body["summary"]["diversification_note"] == "No open holdings yet."

    def test_synthetic_data_provenance_is_reported(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """The UI must be able to label generated prices as generated."""
        assert portfolio(seeded_client, api)["market_data_is_synthetic"] is True


class TestCostBasis:
    def test_a_single_buy_includes_fees_in_the_cost_basis(
        self, seeded_client: TestClient, api: str
    ) -> None:
        # 100 x 800 = 80,000 + 250 fees = 80,250 basis; 802.50 per share.
        buy(seeded_client, api, quantity="100", price="800", fees="250")

        position = holding(portfolio(seeded_client, api), "LUCK")

        assert Decimal(position["quantity"]) == Decimal("100")
        assert Decimal(position["cost_basis"]) == Decimal("80250.00")
        assert Decimal(position["average_cost"]) == Decimal("802.50")

    def test_two_buys_average_out(self, seeded_client: TestClient, api: str) -> None:
        # 100 x 800 = 80,000 and 100 x 900 = 90,000 -> 170,000 over 200 shares = 850.
        buy(seeded_client, api, quantity="100", price="800")
        buy(seeded_client, api, quantity="100", price="900")

        position = holding(portfolio(seeded_client, api), "LUCK")

        assert Decimal(position["quantity"]) == Decimal("200")
        assert Decimal(position["cost_basis"]) == Decimal("170000.00")
        assert Decimal(position["average_cost"]) == Decimal("850.00")

    def test_unrealised_profit_is_measured_against_the_latest_close(
        self, seeded_client: TestClient, api: str
    ) -> None:
        # basis 80,250; market value 100 x 892 = 89,200; gain 8,950 = 11.15%.
        buy(seeded_client, api, quantity="100", price="800", fees="250")

        position = holding(portfolio(seeded_client, api), "LUCK")

        assert Decimal(position["last_price"]) == LUCK_CLOSE
        assert Decimal(position["market_value"]) == Decimal("89200.00")
        assert Decimal(position["unrealised_pl"]) == Decimal("8950.00")
        assert Decimal(position["unrealised_pl_pct"]) == Decimal("11.15")

    def test_a_loss_is_reported_as_a_loss(self, seeded_client: TestClient, api: str) -> None:
        # Bought above the current price: 100 x 1000 = 100,000 vs 89,200.
        buy(seeded_client, api, quantity="100", price="1000")

        position = holding(portfolio(seeded_client, api), "LUCK")

        assert Decimal(position["unrealised_pl"]) == Decimal("-10800.00")
        assert Decimal(position["unrealised_pl_pct"]) == Decimal("-10.80")


class TestRealisedProfit:
    def test_a_partial_sell_banks_profit_and_leaves_average_cost_unchanged(
        self, seeded_client: TestClient, api: str
    ) -> None:
        # Buy 100 @ 800 + 250 fees -> basis 80,250, average 802.50.
        # Sell 40 @ 900 - 100 fees -> proceeds 35,900; cost of those 40 = 32,100.
        # Realised = 35,900 - 32,100 = 3,800. Remaining 60 shares at 802.50 = 48,150.
        buy(seeded_client, api, quantity="100", price="800", fees="250")
        sell(seeded_client, api, quantity="40", price="900", fees="100")

        position = holding(portfolio(seeded_client, api), "LUCK")

        assert Decimal(position["quantity"]) == Decimal("60")
        assert Decimal(position["realised_pl"]) == Decimal("3800.00")
        assert Decimal(position["cost_basis"]) == Decimal("48150.00")
        assert Decimal(position["average_cost"]) == Decimal("802.50")

    def test_a_full_exit_closes_the_position_but_keeps_the_realised_result(
        self, seeded_client: TestClient, api: str
    ) -> None:
        # Buy 100 @ 800, sell 100 @ 900 -> realised 10,000, nothing held.
        buy(seeded_client, api, quantity="100", price="800")
        sell(seeded_client, api, quantity="100", price="900")

        body = portfolio(seeded_client, api)

        assert body["holdings"] == []
        assert body["summary"]["holdings_count"] == 0
        assert Decimal(body["summary"]["total_realised_pl"]) == Decimal("10000.00")

    def test_a_realised_loss_is_reported(self, seeded_client: TestClient, api: str) -> None:
        buy(seeded_client, api, quantity="100", price="900")
        sell(seeded_client, api, quantity="100", price="800")

        summary = portfolio(seeded_client, api)["summary"]
        assert Decimal(summary["total_realised_pl"]) == Decimal("-10000.00")

    def test_fees_on_both_legs_are_totalled(self, seeded_client: TestClient, api: str) -> None:
        buy(seeded_client, api, quantity="100", price="800", fees="250")
        sell(seeded_client, api, quantity="100", price="900", fees="300")

        summary = portfolio(seeded_client, api)["summary"]
        assert Decimal(summary["total_fees_paid"]) == Decimal("550.00")
        # Gross 10,000 less 550 of costs - what the user actually keeps.
        assert Decimal(summary["total_realised_pl"]) == Decimal("9450.00")

    def test_selling_more_than_is_held_is_rejected_at_entry(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """Rejected on the way in, so the ledger stays trustworthy."""
        buy(seeded_client, api, quantity="100", price="800")

        response = seeded_client.post(
            f"{api}/portfolio/trades",
            json={"symbol": "LUCK", "side": "sell", "quantity": "101", "price": "900"},
        )

        assert response.status_code == 422
        body = response.json()["error"]
        assert body["code"] == "validation_error"
        assert body["details"]["quantity_held"].startswith("100")

    def test_selling_a_company_never_bought_is_rejected(
        self, seeded_client: TestClient, api: str
    ) -> None:
        response = seeded_client.post(
            f"{api}/portfolio/trades",
            json={"symbol": "HBL", "side": "sell", "quantity": "10", "price": "140"},
        )
        assert response.status_code == 422


class TestWeightsAndAllocation:
    def test_weights_are_shares_of_total_market_value(
        self, seeded_client: TestClient, api: str
    ) -> None:
        # LUCK: 100 x 892 = 89,200 (cement). FFC: 200 x 148.30 = 29,660 (fertilizer).
        # Total 118,860 -> LUCK 75.05%, FFC 24.95%.
        buy(seeded_client, api, "LUCK", quantity="100", price="800")
        buy(seeded_client, api, "FFC", quantity="200", price="140")

        body = portfolio(seeded_client, api)

        assert Decimal(holding(body, "LUCK")["weight_pct"]) == Decimal("75.05")
        assert Decimal(holding(body, "FFC")["weight_pct"]) == Decimal("24.95")
        total = sum(Decimal(item["weight_pct"]) for item in body["holdings"])
        assert total == pytest.approx(Decimal("100"), abs=Decimal("0.05"))

    def test_holdings_are_ordered_largest_first(self, seeded_client: TestClient, api: str) -> None:
        buy(seeded_client, api, "FFC", quantity="10", price="140")
        buy(seeded_client, api, "LUCK", quantity="100", price="800")

        body = portfolio(seeded_client, api)
        assert [item["symbol"] for item in body["holdings"]] == ["LUCK", "FFC"]

    def test_sector_allocation_groups_holdings(self, seeded_client: TestClient, api: str) -> None:
        buy(seeded_client, api, "LUCK", quantity="50", price="800")
        buy(seeded_client, api, "DGKC", quantity="500", price="90")
        buy(seeded_client, api, "FFC", quantity="100", price="140")

        body = portfolio(seeded_client, api)
        by_sector = {item["sector"]: item for item in body["sector_allocations"]}

        assert by_sector["cement"]["holdings_count"] == 2
        assert by_sector["fertilizer"]["holdings_count"] == 1
        assert body["summary"]["sectors_held"] == 2

    def test_allocations_are_ordered_by_weight(self, seeded_client: TestClient, api: str) -> None:
        buy(seeded_client, api, "LUCK", quantity="100", price="800")
        buy(seeded_client, api, "FFC", quantity="10", price="140")

        allocations = portfolio(seeded_client, api)["sector_allocations"]
        weights = [Decimal(item["weight_pct"]) for item in allocations]
        assert weights == sorted(weights, reverse=True)


class TestConcentrationWarnings:
    def test_a_single_holding_portfolio_is_called_out(
        self, seeded_client: TestClient, api: str
    ) -> None:
        buy(seeded_client, api, "LUCK", quantity="100", price="800")

        note = portfolio(seeded_client, api)["summary"]["diversification_note"]
        assert "entire portfolio is one company" in note

    def test_a_position_over_the_users_own_limit_raises_a_warning(
        self, seeded_client: TestClient, api: str
    ) -> None:
        set_profile(seeded_client, api, max_position_pct="15", max_sector_pct="80")
        buy(seeded_client, api, "LUCK", quantity="100", price="800")
        buy(seeded_client, api, "FFC", quantity="100", price="140")

        warnings = portfolio(seeded_client, api)["concentration_warnings"]
        position_warnings = [item for item in warnings if item["kind"] == "position"]

        assert [item["subject"] for item in position_warnings] == ["LUCK"]
        assert Decimal(position_warnings[0]["limit_pct"]) == Decimal("15.00")
        assert "risk management" in position_warnings[0]["message"]

    def test_a_sector_over_the_users_own_limit_raises_a_warning(
        self, seeded_client: TestClient, api: str
    ) -> None:
        # The position cap cannot exceed the sector cap (a profile-level rule), so
        # both are set to 50% and the assertion filters to sector warnings only.
        set_profile(seeded_client, api, max_position_pct="50", max_sector_pct="50")
        buy(seeded_client, api, "LUCK", quantity="100", price="800")
        buy(seeded_client, api, "FFC", quantity="10", price="140")

        warnings = portfolio(seeded_client, api)["concentration_warnings"]
        sector_warnings = [item for item in warnings if item["kind"] == "sector"]

        assert [item["subject"] for item in sector_warnings] == ["Cement"]
        assert "fall together" in sector_warnings[0]["message"]

    def test_generous_limits_produce_no_warnings(self, seeded_client: TestClient, api: str) -> None:
        set_profile(seeded_client, api, max_position_pct="90", max_sector_pct="95")
        buy(seeded_client, api, "LUCK", quantity="100", price="800")
        buy(seeded_client, api, "FFC", quantity="100", price="140")

        assert portfolio(seeded_client, api)["concentration_warnings"] == []


class TestExitRuleLevels:
    def test_a_holding_without_a_plan_is_flagged_as_having_no_exit_rules(
        self, seeded_client: TestClient, api: str
    ) -> None:
        buy(seeded_client, api, "LUCK", quantity="100", price="800")

        body = portfolio(seeded_client, api)
        position = holding(body, "LUCK")

        assert position["missing_exit_rules"] is True
        assert position["plan_id"] is None
        assert position["profit_target_price"] is None
        assert position["stop_loss_price"] is None
        assert body["summary"]["holdings_without_exit_rules"] == 1

    def test_plan_percentages_are_resolved_to_prices_against_average_cost(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """The guide phrases both rules relative to what you paid."""
        plan = seeded_client.post(f"{api}/plans", json={"symbol": "LUCK"}).json()
        seeded_client.patch(
            f"{api}/plans/{plan['id']}",
            json={
                "understands_business": True,
                "revenue_and_profit_healthy": True,
                "debt_manageable_vs_peers": True,
                "comfortable_with_drawdown": True,
                "position_size_appropriate": True,
                "profit_target_pct": "25",
                "stop_loss_pct": "15",
            },
        )
        assert seeded_client.post(f"{api}/plans/{plan['id']}/commit").status_code == 200

        # 100 @ 800 with no fees -> average cost 800.
        # Target = 800 x 1.25 = 1,000. Stop = 800 x 0.85 = 680.
        buy(seeded_client, api, "LUCK", quantity="100", price="800")

        position = holding(portfolio(seeded_client, api), "LUCK")

        assert position["missing_exit_rules"] is False
        assert position["plan_id"] == plan["id"]
        assert Decimal(position["profit_target_price"]) == Decimal("1000.00")
        assert Decimal(position["stop_loss_price"]) == Decimal("680.00")
        # Price 892: target is 12.11% above, stop is 23.77% below.
        assert Decimal(position["distance_to_target_pct"]) == Decimal("12.11")
        assert Decimal(position["distance_to_stop_pct"]) == Decimal("23.77")


class TestTradeLedger:
    def test_trades_are_listed_newest_first(self, seeded_client: TestClient, api: str) -> None:
        buy(seeded_client, api, "LUCK", quantity="100", price="800")
        buy(seeded_client, api, "FFC", quantity="100", price="140")

        rows = seeded_client.get(f"{api}/portfolio/trades").json()
        assert [row["symbol"] for row in rows] == ["FFC", "LUCK"]

    def test_a_trade_reports_its_signed_cash_effect(
        self, seeded_client: TestClient, api: str
    ) -> None:
        purchase = buy(seeded_client, api, quantity="100", price="800", fees="250")
        assert Decimal(purchase["gross_value"]) == Decimal("80000.00")
        assert Decimal(purchase["net_cash_flow"]) == Decimal("-80250.00")

        disposal = sell(seeded_client, api, quantity="100", price="900", fees="300")
        assert Decimal(disposal["net_cash_flow"]) == Decimal("89700.00")

    def test_a_back_dated_trade_is_accepted(self, seeded_client: TestClient, api: str) -> None:
        """Positions bought before using the tool have to be recordable."""
        response = seeded_client.post(
            f"{api}/portfolio/trades",
            json={
                "symbol": "LUCK",
                "side": "buy",
                "quantity": "100",
                "price": "600",
                "executed_at": "2023-04-11T10:30:00Z",
                "note": "Imported from a broker statement.",
            },
        )
        assert response.status_code == 201
        assert response.json()["executed_at"].startswith("2023-04-11")

    def test_back_dated_trades_replay_in_execution_order_not_entry_order(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """A correction entered late must not change the cost basis."""
        buy(seeded_client, api, quantity="100", price="900")
        seeded_client.post(
            f"{api}/portfolio/trades",
            json={
                "symbol": "LUCK",
                "side": "buy",
                "quantity": "100",
                "price": "700",
                "executed_at": "2024-01-05T09:00:00Z",
            },
        )

        # Average of 700 and 900 regardless of which was recorded first.
        position = holding(portfolio(seeded_client, api), "LUCK")
        assert Decimal(position["average_cost"]) == Decimal("800.00")

    def test_unknown_symbol_is_a_404(self, seeded_client: TestClient, api: str) -> None:
        response = seeded_client.post(
            f"{api}/portfolio/trades",
            json={"symbol": "NOSUCH", "side": "buy", "quantity": "1", "price": "1"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "company_not_found"

    @pytest.mark.parametrize(
        "payload",
        [
            {"symbol": "LUCK", "side": "buy", "quantity": "0", "price": "800"},
            {"symbol": "LUCK", "side": "buy", "quantity": "-5", "price": "800"},
            {"symbol": "LUCK", "side": "buy", "quantity": "10", "price": "0"},
            {"symbol": "LUCK", "side": "buy", "quantity": "10", "price": "800", "fees": "-1"},
            {"symbol": "LUCK", "side": "hold", "quantity": "10", "price": "800"},
        ],
    )
    def test_nonsensical_trades_are_rejected(
        self, seeded_client: TestClient, api: str, payload: dict
    ) -> None:
        response = seeded_client.post(f"{api}/portfolio/trades", json=payload)
        assert response.status_code == 422

    def test_a_trade_cannot_reference_another_companys_plan(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = seeded_client.post(f"{api}/plans", json={"symbol": "FFC"}).json()

        response = seeded_client.post(
            f"{api}/portfolio/trades",
            json={
                "symbol": "LUCK",
                "side": "buy",
                "quantity": "10",
                "price": "800",
                "plan_id": plan["id"],
            },
        )

        assert response.status_code == 422
        assert "different company" in response.json()["error"]["message"]

    def test_a_trade_cannot_reference_a_missing_plan(
        self, seeded_client: TestClient, api: str
    ) -> None:
        response = seeded_client.post(
            f"{api}/portfolio/trades",
            json={
                "symbol": "LUCK",
                "side": "buy",
                "quantity": "10",
                "price": "800",
                "plan_id": 9999,
            },
        )
        assert response.status_code == 422


class TestSummary:
    def test_totals_reconcile_with_the_individual_holdings(
        self, seeded_client: TestClient, api: str
    ) -> None:
        buy(seeded_client, api, "LUCK", quantity="100", price="800", fees="250")
        buy(seeded_client, api, "FFC", quantity="200", price="140", fees="150")

        body = portfolio(seeded_client, api)
        summary = body["summary"]

        assert summary["holdings_count"] == 2
        assert Decimal(summary["total_cost_basis"]) == sum(
            Decimal(item["cost_basis"]) for item in body["holdings"]
        )
        assert Decimal(summary["total_market_value"]) == sum(
            Decimal(item["market_value"]) for item in body["holdings"]
        )
        assert Decimal(summary["total_unrealised_pl"]) == sum(
            Decimal(item["unrealised_pl"]) for item in body["holdings"]
        )
        assert Decimal(summary["total_fees_paid"]) == Decimal("400.00")

    def test_valuation_timestamp_is_present_once_something_is_held(
        self, seeded_client: TestClient, api: str
    ) -> None:
        buy(seeded_client, api, quantity="100", price="800")
        assert portfolio(seeded_client, api)["valued_at"] is not None
