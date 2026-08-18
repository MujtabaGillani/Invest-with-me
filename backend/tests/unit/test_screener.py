"""Unit tests for the simplified buy/sell screen.

Two things are being protected here, and they are not the same thing:

1. **The ranking and the prose are correct** - order, plain-language reasons, and
   the arithmetic behind a suggested position size.
2. **The product line holds.** No response may contain a prediction, a price
   target framed as a forecast, or advice. That is easy to break later with a
   well-meaning "expected return" field, so it is asserted explicitly rather than
   left to review.

Doubles are hand-written rather than mocked: the service composes two other
services, and a fake with three attributes documents the coupling better than a
mock whose interface is invisible.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.analysis.rules import SuggestionRules
from app.core.enums import MetricVerdict, Sector
from app.schemas.analysis import (
    FundamentalsReport,
    FundamentalsScore,
    MetricAssessment,
    StatementReview,
)
from app.schemas.portfolio import (
    ConcentrationWarning,
    HoldingRead,
    PortfolioRead,
    PortfolioSummary,
)
from app.services.screener import ScreenerService


def metric(key: str, verdict: MetricVerdict) -> MetricAssessment:
    return MetricAssessment(
        key=key,
        label=key.replace("_", " ").title(),
        verdict=verdict,
        what_it_measures="x",
        criteria="y",
        commentary="z",
    )


def report(
    symbol: str,
    *,
    strong: list[str] | None = None,
    weak: list[str] | None = None,
    unknown: list[str] | None = None,
    adequate: list[str] | None = None,
    price: Decimal | None = Decimal("100"),
    sector: Sector = Sector.CEMENT,
) -> FundamentalsReport:
    """A fundamentals report with the verdicts a test cares about."""
    metrics = (
        [metric(key, MetricVerdict.STRONG) for key in strong or []]
        + [metric(key, MetricVerdict.ADEQUATE) for key in adequate or []]
        + [metric(key, MetricVerdict.WEAK) for key in weak or []]
        + [metric(key, MetricVerdict.INSUFFICIENT_DATA) for key in unknown or []]
    )
    return FundamentalsReport(
        symbol=symbol,
        company_name=f"{symbol} Limited",
        sector=sector,
        sector_label=sector.value.replace("_", " ").title(),
        fiscal_years=[2024, 2025],
        latest_fiscal_year=2025,
        reference_price=price,
        reference_price_date=date(2026, 8, 18),
        peer_count=3,
        metrics=metrics,
        # Required by the schema and unused by the screener, which reads only
        # ``metrics`` and ``score``.
        statement_review=StatementReview(
            checks=[], failed_count=0, unknown_count=0, needs_investigation=False, summary=""
        ),
        red_flags=[],
        score=FundamentalsScore(
            strong=len(strong or []),
            adequate=len(adequate or []),
            weak=len(weak or []),
            insufficient_data=len(unknown or []),
            metrics_assessed=len(metrics),
        ),
    )


def holding(
    symbol: str,
    *,
    price: Decimal | None = Decimal("100"),
    target: Decimal | None = None,
    stop: Decimal | None = None,
    pl_pct: Decimal | None = Decimal("10"),
    missing_exit_rules: bool = False,
) -> HoldingRead:
    return HoldingRead(
        company_id=1,
        symbol=symbol,
        company_name=f"{symbol} Limited",
        sector=Sector.CEMENT,
        sector_label="Cement",
        quantity=Decimal("100"),
        average_cost=Decimal("90"),
        cost_basis=Decimal("9000"),
        last_price=price,
        unrealised_pl=Decimal("1000"),
        unrealised_pl_pct=pl_pct,
        profit_target_price=target,
        stop_loss_price=stop,
        missing_exit_rules=missing_exit_rules,
    )


def portfolio_read(
    holdings: list[HoldingRead], warnings: list[ConcentrationWarning] | None = None
) -> PortfolioRead:
    return PortfolioRead(
        summary=PortfolioSummary(
            holdings_count=len(holdings),
            sectors_held=1,
            total_cost_basis=Decimal("9000"),
            total_market_value=Decimal("10000"),
            total_unrealised_pl=Decimal("1000"),
            total_realised_pl=Decimal("0"),
            total_fees_paid=Decimal("0"),
            diversification_note="note",
        ),
        holdings=holdings,
        sector_allocations=[],
        concentration_warnings=warnings or [],
        market_data_is_synthetic=False,
    )


class FakeAnalysis:
    def __init__(self, reports: dict[str, FundamentalsReport]) -> None:
        self._reports = reports

    def bulk_fundamentals(self, symbols: Any) -> dict[str, FundamentalsReport]:
        return {s: self._reports[s] for s in symbols if s in self._reports}

    def technicals(self, _symbol: str) -> Any:
        raise RuntimeError("no technicals in this test")


class FakePortfolio:
    def __init__(self, portfolio: PortfolioRead, value: Decimal = Decimal("100000")) -> None:
        self._portfolio = portfolio
        self._value = value

    def get_portfolio(self, _user_id: int, **_kwargs: Any) -> PortfolioRead:
        return self._portfolio

    def portfolio_value(self, _user_id: int) -> Decimal:
        return self._value


class FakeCompanies:
    def __init__(self, symbols: list[str]) -> None:
        self._symbols = symbols

    def search(self, **_kwargs: Any) -> tuple[list[Any], int]:
        return ([type("C", (), {"symbol": s})() for s in self._symbols], len(self._symbols))


class FakeProfiles:
    def __init__(self, capital: Decimal = Decimal("1000000"), max_pct: Decimal = Decimal("15")):
        self._profile = type(
            "P", (), {"investable_capital": capital, "max_position_pct": max_pct}
        )()

    def get_for_user(self, _user_id: int) -> Any:
        return self._profile


def build(
    reports: dict[str, FundamentalsReport],
    holdings: list[HoldingRead] | None = None,
    warnings: list[ConcentrationWarning] | None = None,
    *,
    rules: SuggestionRules | None = None,
    capital: Decimal = Decimal("1000000"),
) -> ScreenerService:
    pf = portfolio_read(holdings or [], warnings)
    service = ScreenerService(
        session=None,  # type: ignore[arg-type]
        analysis=FakeAnalysis(reports),  # type: ignore[arg-type]
        portfolio=FakePortfolio(pf),  # type: ignore[arg-type]
        rules=rules or SuggestionRules(),
        price_delay_minutes=15,
        data_is_synthetic=False,
    )
    service.companies = FakeCompanies(sorted(reports))  # type: ignore[assignment]
    service.profiles = FakeProfiles(capital)  # type: ignore[assignment]
    return service


# --- Ranking --------------------------------------------------------------


def test_ranks_by_criteria_met() -> None:
    reports = {
        "AAA": report("AAA", strong=["net_margin", "dividend"], weak=["pe_ratio"]),
        "BBB": report("BBB", strong=["net_margin", "dividend", "pe_ratio", "eps_trend"]),
        "CCC": report("CCC", strong=["net_margin", "dividend", "pe_ratio"]),
    }
    result = build(reports).buy_candidates(1)
    assert [c.symbol for c in result.candidates] == ["BBB", "CCC", "AAA"]


def test_a_company_we_can_see_outranks_one_we_cannot() -> None:
    """Equal strong counts: fewer unknowns wins.

    Otherwise a company with two passing checks and five unreadable ones would tie
    with one that passed two and failed none, which reads as equal confidence.
    """
    reports = {
        "SEEN": report("SEEN", strong=["net_margin", "dividend"]),
        "MURKY": report(
            "MURKY",
            strong=["net_margin", "dividend"],
            unknown=["pe_ratio", "eps_trend", "free_cash_flow"],
        ),
    }
    result = build(reports).buy_candidates(1)
    assert [c.symbol for c in result.candidates] == ["SEEN", "MURKY"]


def test_excludes_companies_below_the_minimum_checks() -> None:
    reports = {
        "GOOD": report("GOOD", strong=["net_margin", "dividend"]),
        "THIN": report("THIN", strong=["net_margin"], weak=["pe_ratio"]),
    }
    result = build(reports, rules=SuggestionRules(min_strong_checks=2)).buy_candidates(1)
    assert [c.symbol for c in result.candidates] == ["GOOD"]


def test_respects_the_limit() -> None:
    reports = {
        f"S{i}": report(f"S{i}", strong=["net_margin", "dividend", "pe_ratio"]) for i in range(8)
    }
    assert len(build(reports).buy_candidates(1, limit=3).candidates) == 3


def test_reports_how_many_companies_could_not_be_assessed() -> None:
    """A skipped company must be counted, not silently dropped."""
    service = build({"AAA": report("AAA", strong=["net_margin", "dividend"])})
    service.companies = FakeCompanies(["AAA", "NODATA1", "NODATA2"])  # type: ignore[assignment]
    result = service.buy_candidates(1)
    assert result.companies_scanned == 3
    assert result.companies_skipped == 2


def test_marks_companies_already_owned() -> None:
    reports = {"AAA": report("AAA", strong=["net_margin", "dividend"])}
    result = build(reports, holdings=[holding("AAA")]).buy_candidates(1)
    assert result.candidates[0].already_owned is True


# --- Plain language -------------------------------------------------------


def test_explains_each_passing_check_in_plain_words() -> None:
    reports = {"AAA": report("AAA", strong=["revenue_growth", "free_cash_flow"])}
    why = build(reports).buy_candidates(1).candidates[0].why
    assert "Sales have been growing steadily" in why
    assert "Generates real cash, not just paper profit" in why
    # No jargon leaking through from the metric keys.
    assert not any("_" in sentence for sentence in why)


def test_names_the_missing_data_instead_of_counting_it() -> None:
    """ "3 checks unavailable" invites assuming the missing ones were fine."""
    reports = {"AAA": report("AAA", strong=["net_margin", "dividend"], unknown=["free_cash_flow"])}
    watch = build(reports).buy_candidates(1).candidates[0].watch_out_for
    assert any("cash flow" in line for line in watch)


def test_weak_checks_are_surfaced_not_hidden() -> None:
    reports = {"AAA": report("AAA", strong=["net_margin", "dividend"], weak=["debt_to_equity"])}
    watch = build(reports).buy_candidates(1).candidates[0].watch_out_for
    assert "Carrying a lot of debt" in watch


def test_separates_source_wide_gaps_from_company_specific_ones() -> None:
    """A check no company can satisfy is a fact about the data source."""
    reports = {
        "AAA": report("AAA", strong=["net_margin", "dividend"], unknown=["free_cash_flow"]),
        "BBB": report("BBB", strong=["net_margin", "dividend"], unknown=["free_cash_flow"]),
    }
    result = build(reports).buy_candidates(1)
    assert result.unavailable_checks == ["cash flow"]


def test_a_gap_in_one_company_only_is_not_reported_as_source_wide() -> None:
    reports = {
        "AAA": report("AAA", strong=["net_margin", "dividend"], unknown=["free_cash_flow"]),
        "BBB": report("BBB", strong=["net_margin", "dividend"]),
    }
    assert build(reports).buy_candidates(1).unavailable_checks == []


# --- Suggested entry ------------------------------------------------------


def test_suggests_a_size_from_the_users_own_limit() -> None:
    reports = {"AAA": report("AAA", strong=["net_margin", "dividend"], price=Decimal("100"))}
    suggested = build(reports, capital=Decimal("1000000")).buy_candidates(1).candidates[0].suggested
    assert suggested is not None
    # 15% of the larger of portfolio value (100k) and capital (1m).
    assert suggested.suggested_amount == Decimal("150000.00")
    assert suggested.suggested_shares == 1500


def test_suggested_shares_are_whole_and_rounded_down() -> None:
    """Rounded down: rounding up would suggest a purchase over the user's limit."""
    reports = {"AAA": report("AAA", strong=["net_margin", "dividend"], price=Decimal("700"))}
    suggested = build(reports, capital=Decimal("10000")).buy_candidates(1).candidates[0].suggested
    assert suggested is not None
    # Base is the larger of portfolio value (100,000) and capital (10,000), so the
    # 15% limit is 15,000; 15000/700 = 21.43, floored.
    assert suggested.suggested_shares == 21


def test_target_and_stop_come_from_the_rules_not_a_forecast() -> None:
    reports = {"AAA": report("AAA", strong=["net_margin", "dividend"], price=Decimal("100"))}
    rules = SuggestionRules(profit_target_pct=Decimal("25"), stop_loss_pct=Decimal("15"))
    suggested = build(reports, rules=rules).buy_candidates(1).candidates[0].suggested
    assert suggested is not None
    assert suggested.profit_target_price == Decimal("125.00")
    assert suggested.stop_loss_price == Decimal("85.00")
    assert "not forecasts" in suggested.basis


def test_no_price_means_no_invented_levels() -> None:
    reports = {"AAA": report("AAA", strong=["net_margin", "dividend"], price=None)}
    suggested = build(reports).buy_candidates(1).candidates[0].suggested
    assert suggested is not None
    assert suggested.profit_target_price is None
    assert suggested.stop_loss_price is None
    assert suggested.suggested_shares is None


# --- Sell review ----------------------------------------------------------


def test_flags_a_reached_profit_target() -> None:
    holdings = [holding("AAA", price=Decimal("130"), target=Decimal("125"), stop=Decimal("85"))]
    items = build({}, holdings=holdings).sell_review(1).items
    reached = [i for i in items if i.reason == "profit_target_reached"]
    assert len(reached) == 1
    assert reached[0].urgency == "act_now"
    assert "reached the profit target you set" in reached[0].headline


def test_flags_a_breached_stop_loss() -> None:
    holdings = [holding("AAA", price=Decimal("80"), target=Decimal("125"), stop=Decimal("85"))]
    items = build({}, holdings=holdings).sell_review(1).items
    breached = [i for i in items if i.reason == "stop_loss_breached"]
    assert len(breached) == 1
    assert breached[0].urgency == "act_now"


def test_a_holding_between_its_rules_raises_nothing() -> None:
    holdings = [holding("AAA", price=Decimal("100"), target=Decimal("125"), stop=Decimal("85"))]
    assert build({}, holdings=holdings).sell_review(1).items == []


def test_exit_rules_are_inclusive_at_the_boundary() -> None:
    """At exactly the target, the rule has been met.

    A strict comparison would leave a holding sitting on its own target reporting
    nothing, which is the one moment the user asked to be told about.
    """
    at_target = [holding("AAA", price=Decimal("125"), target=Decimal("125"), stop=Decimal("85"))]
    target_items = build({}, holdings=at_target).sell_review(1).items
    assert any(item.reason == "profit_target_reached" for item in target_items)

    at_stop = [holding("BBB", price=Decimal("85"), target=Decimal("125"), stop=Decimal("85"))]
    stop_items = build({}, holdings=at_stop).sell_review(1).items
    assert any(item.reason == "stop_loss_breached" for item in stop_items)


def test_a_holding_with_no_exit_rules_is_surfaced() -> None:
    holdings = [holding("AAA", missing_exit_rules=True)]
    items = build({}, holdings=holdings).sell_review(1).items
    assert [i.reason for i in items] == ["no_exit_rules"]
    assert items[0].urgency == "decide_soon", "not urgent, but it is a decision"


def test_crossed_rules_sort_above_things_that_merely_need_a_decision() -> None:
    holdings = [
        holding("SOON", missing_exit_rules=True, pl_pct=Decimal("90")),
        holding("NOW", price=Decimal("130"), target=Decimal("125"), pl_pct=Decimal("5")),
    ]
    items = build({}, holdings=holdings).sell_review(1).items
    assert items[0].symbol == "NOW", "a crossed rule outranks a larger move with no rule"


def test_concentration_is_a_reason_to_trim_never_act_now() -> None:
    warnings = [
        ConcentrationWarning(
            kind="position",
            subject="AAA",
            weight_pct=Decimal("25"),
            limit_pct=Decimal("15"),
            message="AAA is 25% of your portfolio.",
        )
    ]
    items = build({}, holdings=[holding("AAA")], warnings=warnings).sell_review(1).items
    trim = [i for i in items if i.reason == "position_too_large"]
    assert len(trim) == 1
    assert trim[0].urgency == "decide_soon"


def test_sector_warnings_without_a_matching_holding_are_skipped() -> None:
    warnings = [
        ConcentrationWarning(
            kind="sector",
            subject="Cement",
            weight_pct=Decimal("60"),
            limit_pct=Decimal("35"),
            message="Cement is 60% of your portfolio.",
        )
    ]
    items = build({}, holdings=[holding("AAA")], warnings=warnings).sell_review(1).items
    assert all(i.reason != "position_too_large" for i in items)


@pytest.mark.parametrize(
    ("pl_pct", "expected"),
    [
        (Decimal("12.5"), "up 12.50% on what you paid"),
        (Decimal("-12.5"), "down 12.50% on what you paid"),
        (Decimal("0"), "level with what you paid"),
        (None, "standing is unknown"),
    ],
)
def test_standing_reads_as_english_not_a_signed_number(
    pl_pct: Decimal | None, expected: str
) -> None:
    holdings = [holding("AAA", missing_exit_rules=True, pl_pct=pl_pct)]
    headline = build({}, holdings=holdings).sell_review(1).items[0].headline
    assert expected in headline


# --- The product line -----------------------------------------------------


def test_responses_carry_the_provider_honesty_flags() -> None:
    """A ranked list of delayed or invented figures must say so."""
    reports = {"AAA": report("AAA", strong=["net_margin", "dividend"])}
    buy = build(reports).buy_candidates(1)
    sell = build(reports, holdings=[holding("AAA")]).sell_review(1)
    for response in (buy, sell):
        assert response.price_delay_minutes == 15
        assert response.data_is_synthetic is False


def test_nothing_in_the_response_claims_to_predict() -> None:
    """Guards the constraint against a future well-meaning 'expected return'.

    The disclaimers are excluded from the scan on purpose: they *deny* prediction,
    so "no tool can tell you which shares will be profitable" is the sentence we
    want, not a violation. Everything else - every candidate row, every field - is
    fair game.
    """
    reports = {"AAA": report("AAA", strong=["net_margin", "dividend"])}
    result = build(reports).buy_candidates(1)
    payload = result.model_copy(update={"disclaimer": ""}).model_dump_json().lower()
    for forbidden in (
        "expected return",
        "will rise",
        "will be profitable",
        "predicted",
        "recommend",
        "guaranteed",
    ):
        assert forbidden not in payload, f"response contains {forbidden!r}"


def test_the_disclaimer_says_no_tool_can_do_this() -> None:
    reports = {"AAA": report("AAA", strong=["net_margin", "dividend"])}
    disclaimer = build(reports).buy_candidates(1).disclaimer.lower()
    assert "not a prediction" in disclaimer
    assert "no tool" in disclaimer


def test_sell_review_says_the_app_does_not_decide() -> None:
    disclaimer = build({}, holdings=[holding("AAA")]).sell_review(1).disclaimer.lower()
    assert "does not decide" in disclaimer
