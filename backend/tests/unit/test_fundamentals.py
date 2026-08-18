"""Fundamentals checklist rules.

The emphasis here is on the judgements a reviewer would want proof of:

* a criterion that is *not* met is reported as WEAK
* a criterion that *cannot be assessed* is reported as INSUFFICIENT_DATA, never as
  WEAK - conflating "we don't know" with "it's bad" is the failure mode that would
  make this tool actively misleading
* the sector-relative rules behave for banks, which are structurally leveraged
"""

from __future__ import annotations

import pytest

from app.analysis.fundamentals import (
    assess_debt_to_equity,
    assess_dividends,
    assess_eps_trend,
    assess_free_cash_flow,
    assess_net_margin,
    assess_pe_ratio,
    assess_revenue_growth,
    build_fundamentals_report,
    detect_red_flags,
    review_statements,
    sector_medians,
)
from app.analysis.inputs import FinancialYear, FundamentalsInput, PeerStatistics
from app.core.enums import MetricVerdict, Sector

pytestmark = pytest.mark.unit


def year(
    fiscal_year: int,
    *,
    revenue: float | None = None,
    net_profit: float | None = None,
    eps: float | None = None,
    equity: float | None = None,
    debt: float | None = None,
    ocf: float | None = None,
    capex: float | None = None,
    dividend: float | None = None,
    shares: float | None = None,
) -> FinancialYear:
    """Build a financial year with only the fields a test cares about."""
    return FinancialYear(
        fiscal_year=fiscal_year,
        revenue=revenue,
        net_profit=net_profit,
        eps=eps,
        total_equity=equity,
        total_debt=debt,
        operating_cash_flow=ocf,
        capital_expenditure=capex,
        dividend_per_share=dividend,
        shares_outstanding=shares,
    )


def growing_years(rate: float = 1.15, count: int = 5, margin: float = 0.15) -> list[FinancialYear]:
    """A steadily growing, profitable, cash-generating company."""
    years: list[FinancialYear] = []
    revenue = 1000.0
    for index in range(count):
        profit = revenue * margin
        years.append(
            year(
                2020 + index,
                revenue=revenue,
                net_profit=profit,
                eps=profit / 100,
                equity=revenue * 1.2,
                debt=revenue * 0.3,
                ocf=profit * 1.2,
                capex=revenue * 0.05,
                dividend=profit / 100 * 0.3,
            )
        )
        revenue *= rate
    return years


class TestRevenueGrowth:
    def test_consistent_double_digit_growth_is_strong(self) -> None:
        result = assess_revenue_growth(growing_years(rate=1.18))
        assert result.verdict is MetricVerdict.STRONG
        assert result.value is not None and result.value > 12.0

    def test_flat_revenue_is_weak(self) -> None:
        years = [year(2020 + i, revenue=1000.0) for i in range(5)]
        assert assess_revenue_growth(years).verdict is MetricVerdict.WEAK

    def test_shrinking_revenue_is_weak(self) -> None:
        years = [year(2020 + i, revenue=1000.0 * (0.9**i)) for i in range(5)]
        result = assess_revenue_growth(years)
        assert result.verdict is MetricVerdict.WEAK
        assert result.value is not None and result.value < 0

    def test_fast_but_erratic_growth_is_only_adequate(self) -> None:
        """The guide asks for consistency, not just a flattering endpoint rate."""
        revenues = [1000.0, 700.0, 900.0, 800.0, 2600.0]
        years = [year(2020 + i, revenue=value) for i, value in enumerate(revenues)]
        result = assess_revenue_growth(years)
        assert result.value is not None and result.value > 20.0  # strong on rate alone
        assert result.verdict is MetricVerdict.ADEQUATE  # downgraded for inconsistency

    def test_two_years_is_not_enough_for_a_trend(self) -> None:
        years = [year(2023, revenue=1000.0), year(2024, revenue=2000.0)]
        assert assess_revenue_growth(years).verdict is MetricVerdict.INSUFFICIENT_DATA

    def test_negative_revenue_base_reports_insufficient_rather_than_a_wild_rate(self) -> None:
        years = [year(2022, revenue=-100.0), year(2023, revenue=500.0), year(2024, revenue=900.0)]
        result = assess_revenue_growth(years)
        assert result.verdict is MetricVerdict.INSUFFICIENT_DATA
        assert "negative" in result.commentary


class TestNetMargin:
    def test_healthy_stable_margin_is_strong(self) -> None:
        assert assess_net_margin(growing_years(margin=0.15)).verdict is MetricVerdict.STRONG

    def test_loss_making_is_weak(self) -> None:
        years = [year(2020 + i, revenue=1000.0, net_profit=-50.0) for i in range(3)]
        result = assess_net_margin(years)
        assert result.verdict is MetricVerdict.WEAK
        assert "loss-making" in result.commentary

    def test_eroding_margin_is_downgraded_despite_a_healthy_level(self) -> None:
        """A 12% margin that used to be 25% is not "strong"."""
        years = [
            year(2020, revenue=1000.0, net_profit=250.0),
            year(2021, revenue=1000.0, net_profit=210.0),
            year(2022, revenue=1000.0, net_profit=170.0),
            year(2023, revenue=1000.0, net_profit=140.0),
            year(2024, revenue=1000.0, net_profit=120.0),
        ]
        result = assess_net_margin(years)
        assert result.value == pytest.approx(12.0)
        assert result.verdict is MetricVerdict.ADEQUATE
        assert "narrowed" in result.commentary

    def test_thin_margin_is_weak(self) -> None:
        years = [year(2020 + i, revenue=1000.0, net_profit=15.0) for i in range(3)]
        assert assess_net_margin(years).verdict is MetricVerdict.WEAK

    def test_no_revenue_reports_insufficient(self) -> None:
        years = [year(2024, net_profit=100.0)]
        assert assess_net_margin(years).verdict is MetricVerdict.INSUFFICIENT_DATA


class TestEpsTrend:
    def test_steady_growth_is_strong(self) -> None:
        years = [year(2020 + i, eps=5.0 + i) for i in range(5)]
        assert assess_eps_trend(years).verdict is MetricVerdict.STRONG

    def test_negative_latest_eps_is_weak(self) -> None:
        years = [year(2020, eps=5.0), year(2021, eps=2.0), year(2022, eps=-1.0)]
        assert assess_eps_trend(years).verdict is MetricVerdict.WEAK

    def test_higher_but_erratic_is_adequate(self) -> None:
        years = [year(2020, eps=5.0), year(2021, eps=2.0), year(2022, eps=1.0), year(2023, eps=8.0)]
        assert assess_eps_trend(years).verdict is MetricVerdict.ADEQUATE

    def test_single_year_reports_insufficient(self) -> None:
        assert assess_eps_trend([year(2024, eps=5.0)]).verdict is MetricVerdict.INSUFFICIENT_DATA

    def test_bonus_issue_is_not_reported_as_weak(self) -> None:
        """A share count that jumps makes the EPS series incomparable, not bad.

        Modelled on Lucky Cement's real filings: profit tripled while reported
        EPS fell, because the share count went from ~319m to ~1.47bn. Scoring
        that as "weak" was a false negative on real PSX data - exchanges publish
        EPS as reported and never restate it after a bonus issue.
        """
        years = [
            year(2023, eps=43.06, shares=318_800_000.0),
            year(2024, eps=18.91, shares=1_486_300_000.0),
            year(2025, eps=22.59, shares=1_464_900_000.0),
            year(2026, eps=31.83, shares=1_465_000_000.0),
        ]
        result = assess_eps_trend(years)
        assert result.verdict is MetricVerdict.INSUFFICIENT_DATA
        assert "bonus issue or a split" in result.commentary
        assert "359" in result.commentary, "reports share-count growth, not shrinkage"
        assert result.history, "the yearly figures are still shown"

    def test_ordinary_dilution_does_not_block_the_comparison(self) -> None:
        """Small issuance is normal and must not suppress the metric."""
        years = [
            year(2023, eps=5.0, shares=100_000_000.0),
            year(2024, eps=6.0, shares=105_000_000.0),
            year(2025, eps=7.0, shares=108_000_000.0),
        ]
        assert assess_eps_trend(years).verdict is MetricVerdict.STRONG

    def test_falling_eps_on_a_stable_share_count_is_still_weak(self) -> None:
        """The guard must not become an excuse that hides genuine decline."""
        years = [
            year(2023, eps=10.0, shares=100_000_000.0),
            year(2024, eps=7.0, shares=100_000_000.0),
            year(2025, eps=4.0, shares=100_000_000.0),
        ]
        assert assess_eps_trend(years).verdict is MetricVerdict.WEAK

    def test_missing_share_counts_judge_eps_at_face_value(self) -> None:
        """Most sources do not publish the share count; the metric still works."""
        years = [year(2023, eps=5.0), year(2024, eps=6.0), year(2025, eps=7.0)]
        assert assess_eps_trend(years).verdict is MetricVerdict.STRONG


class TestPeRatio:
    def test_discount_to_peers_is_strong(self) -> None:
        result = assess_pe_ratio(10.0, 70.0, peer_median_pe=12.0, peer_count=5)
        assert result.value == pytest.approx(7.0)
        assert result.verdict is MetricVerdict.STRONG
        assert result.peer_median == pytest.approx(12.0)

    def test_premium_to_peers_is_weak(self) -> None:
        result = assess_pe_ratio(10.0, 200.0, peer_median_pe=12.0, peer_count=5)
        assert result.verdict is MetricVerdict.WEAK

    def test_in_line_with_peers_is_adequate(self) -> None:
        result = assess_pe_ratio(10.0, 120.0, peer_median_pe=12.0, peer_count=5)
        assert result.verdict is MetricVerdict.ADEQUATE

    def test_loss_making_company_has_no_pe(self) -> None:
        """Never a negative or enormous multiple that a "cheapest" sort would rank first."""
        result = assess_pe_ratio(-3.0, 50.0, peer_median_pe=12.0, peer_count=5)
        assert result.verdict is MetricVerdict.INSUFFICIENT_DATA
        assert result.value is None
        assert "loss" in result.commentary

    def test_too_few_peers_falls_back_to_absolute_bands_and_says_so(self) -> None:
        result = assess_pe_ratio(10.0, 70.0, peer_median_pe=12.0, peer_count=1)
        assert result.verdict is MetricVerdict.STRONG  # 7x is cheap in absolute terms
        assert result.peer_median is None
        assert "sector peers" in result.commentary

    def test_missing_price_reports_insufficient(self) -> None:
        result = assess_pe_ratio(10.0, None, peer_median_pe=12.0, peer_count=5)
        assert result.verdict is MetricVerdict.INSUFFICIENT_DATA


class TestDebtToEquity:
    def test_low_absolute_gearing_is_strong(self) -> None:
        years = [year(2024, equity=1000.0, debt=200.0)]
        result = assess_debt_to_equity(years, False, None, 0)
        assert result.value == pytest.approx(0.2)
        assert result.verdict is MetricVerdict.STRONG

    def test_high_absolute_gearing_is_weak(self) -> None:
        years = [year(2024, equity=1000.0, debt=2500.0)]
        assert assess_debt_to_equity(years, False, None, 0).verdict is MetricVerdict.WEAK

    def test_bank_gearing_is_judged_against_peers_not_absolute_bands(self) -> None:
        """A bank at 8x with peers at 10x is well capitalised, not "weak"."""
        years = [year(2024, equity=1000.0, debt=8000.0)]
        result = assess_debt_to_equity(
            years, sector_uses_peer_comparison=True, peer_median_debt_to_equity=10.0, peer_count=4
        )
        assert result.verdict is MetricVerdict.STRONG
        assert result.peer_median == pytest.approx(10.0)

    def test_bank_without_enough_peers_gets_no_verdict(self) -> None:
        """Better to say "review this manually" than to apply an irrelevant band."""
        years = [year(2024, equity=1000.0, debt=8000.0)]
        result = assess_debt_to_equity(
            years, sector_uses_peer_comparison=True, peer_median_debt_to_equity=10.0, peer_count=1
        )
        assert result.verdict is MetricVerdict.INSUFFICIENT_DATA
        assert "structurally leveraged" in result.commentary

    def test_negative_equity_reports_insufficient_and_explains_itself(self) -> None:
        years = [year(2024, equity=-500.0, debt=1000.0)]
        result = assess_debt_to_equity(years, False, None, 0)
        assert result.verdict is MetricVerdict.INSUFFICIENT_DATA
        assert "negative" in result.commentary


class TestDividends:
    def test_consistent_growing_dividend_is_strong(self) -> None:
        years = [year(2020 + i, dividend=3.0 + i) for i in range(4)]
        result = assess_dividends(years, reference_price=100.0)
        assert result.verdict is MetricVerdict.STRONG
        assert result.value == pytest.approx(6.0)  # 6.00 / 100
        assert result.unit == "%"

    def test_never_paying_a_dividend_is_not_a_negative(self) -> None:
        """A growth company reinvesting everything must not be marked down."""
        years = [year(2020 + i, dividend=0.0) for i in range(4)]
        result = assess_dividends(years, reference_price=100.0)
        assert result.verdict is MetricVerdict.INSUFFICIENT_DATA
        assert "not a negative on its own" in result.commentary

    def test_cutting_the_dividend_is_weak(self) -> None:
        years = [year(2021, dividend=4.0), year(2022, dividend=4.0), year(2023, dividend=0.0)]
        result = assess_dividends(years, reference_price=100.0)
        assert result.verdict is MetricVerdict.WEAK
        assert "worth checking why" in result.commentary


class TestFreeCashFlow:
    def test_consistently_positive_is_strong(self) -> None:
        years = [year(2020 + i, ocf=200.0, capex=50.0) for i in range(4)]
        assert assess_free_cash_flow(years).verdict is MetricVerdict.STRONG

    def test_negative_latest_year_is_weak_but_explained(self) -> None:
        years = [year(2022, ocf=200.0, capex=50.0), year(2023, ocf=100.0, capex=400.0)]
        result = assess_free_cash_flow(years)
        assert result.verdict is MetricVerdict.WEAK
        assert "heavy" in result.commentary  # invites investigation, not a verdict

    def test_missing_cash_flow_reports_insufficient(self) -> None:
        assert (
            assess_free_cash_flow([year(2024, revenue=100.0)]).verdict
            is MetricVerdict.INSUFFICIENT_DATA
        )


class TestStatementReview:
    def test_healthy_company_passes_every_check(self) -> None:
        review = review_statements(growing_years())
        assert review.failed_count == 0
        assert review.unknown_count == 0
        assert review.needs_investigation is False

    def test_two_failures_trigger_the_investigate_rule(self) -> None:
        """The guide's explicit rule: two or more "no" answers is worth investigating."""
        years = [
            year(2022, revenue=1000.0, net_profit=100.0, equity=100.0, debt=900.0, ocf=-10.0),
            year(2023, revenue=900.0, net_profit=40.0, equity=100.0, debt=1100.0, ocf=-30.0),
            year(2024, revenue=800.0, net_profit=10.0, equity=100.0, debt=1400.0, ocf=-50.0),
        ]
        review = review_statements(years)
        assert review.failed_count >= 2
        assert review.needs_investigation is True
        assert "two" in review.summary

    def test_missing_data_is_counted_as_unknown_not_as_failure(self) -> None:
        """Two data gaps must not masquerade as two reasons for concern."""
        review = review_statements([year(2024, revenue=1000.0)])
        assert review.failed_count == 0
        assert review.unknown_count == 4
        assert review.needs_investigation is False


class TestRedFlags:
    def _input(self, years: list[FinancialYear], *, price_change: float | None = None):
        return FundamentalsInput(
            symbol="TEST",
            company_name="Test Co",
            sector=Sector.CEMENT,
            years=tuple(years),
            peers=PeerStatistics(sector=Sector.CEMENT),
            reference_price=100.0,
            price_change_pct_recent=price_change,
        )

    def test_falling_knife_needs_both_a_price_fall_and_deterioration(self) -> None:
        years = [
            year(2023, revenue=1000.0, net_profit=200.0, equity=1000.0, debt=300.0),
            year(2024, revenue=900.0, net_profit=80.0, equity=1000.0, debt=500.0),
        ]
        flags = detect_red_flags(self._input(years, price_change=-35.0))
        assert "falling_knife" in {flag.key for flag in flags}

    def test_price_fall_with_intact_fundamentals_is_flagged_differently(self) -> None:
        """Down 30% on healthy accounts is a question, not a falling knife."""
        years = [
            year(2023, revenue=1000.0, net_profit=150.0, equity=1000.0, debt=300.0),
            year(2024, revenue=1200.0, net_profit=190.0, equity=1200.0, debt=300.0),
        ]
        keys = {flag.key for flag in detect_red_flags(self._input(years, price_change=-30.0))}
        assert "price_decline_unexplained" in keys
        assert "falling_knife" not in keys

    def test_no_price_fall_means_no_knife_flag(self) -> None:
        years = [
            year(2023, revenue=1000.0, net_profit=200.0, equity=1000.0, debt=300.0),
            year(2024, revenue=900.0, net_profit=80.0, equity=1000.0, debt=500.0),
        ]
        keys = {flag.key for flag in detect_red_flags(self._input(years, price_change=-2.0))}
        assert "falling_knife" not in keys

    def test_profit_without_cash_is_flagged(self) -> None:
        years = [year(2024, revenue=1000.0, net_profit=150.0, ocf=-40.0, equity=800.0, debt=100.0)]
        keys = {flag.key for flag in detect_red_flags(self._input(years))}
        assert "profit_without_cash" in keys

    def test_negative_equity_is_critical(self) -> None:
        years = [year(2024, revenue=1000.0, net_profit=10.0, equity=-200.0, debt=900.0)]
        flags = detect_red_flags(self._input(years))
        negative_equity = next(flag for flag in flags if flag.key == "negative_equity")
        assert negative_equity.severity == "critical"

    def test_dividend_funded_from_borrowing_is_flagged(self) -> None:
        years = [year(2024, revenue=1000.0, net_profit=50.0, ocf=20.0, capex=200.0, dividend=2.0)]
        keys = {flag.key for flag in detect_red_flags(self._input(years))}
        assert "dividend_exceeds_cash_generation" in keys

    def test_healthy_company_raises_nothing(self) -> None:
        assert detect_red_flags(self._input(growing_years(), price_change=8.0)) == []


class TestSectorMedians:
    def test_skips_companies_that_cannot_produce_a_given_metric(self) -> None:
        """A loss-maker must be excluded from the P/E median but kept for gearing."""
        profitable = year(2024, eps=10.0, equity=1000.0, debt=500.0, revenue=100.0, net_profit=10.0)
        modest = year(2024, eps=5.0, equity=1000.0, debt=1000.0, revenue=100.0, net_profit=5.0)
        loss_maker = year(
            2024, eps=-2.0, equity=1000.0, debt=1500.0, revenue=100.0, net_profit=-2.0
        )
        pairs = [(profitable, 100.0), (modest, 100.0), (loss_maker, 50.0)]
        median_pe, median_gearing, median_margin = sector_medians(pairs)
        assert median_pe == pytest.approx(15.0)  # median of 10x and 20x
        assert median_gearing == pytest.approx(1.0)  # median of 0.5, 1.0, 1.5
        assert median_margin == pytest.approx(5.0)

    def test_returns_none_for_an_empty_sector(self) -> None:
        assert sector_medians([]) == (None, None, None)


class TestBuildReport:
    def test_report_covers_every_checklist_metric_in_guide_order(self) -> None:
        data = FundamentalsInput(
            symbol="TEST",
            company_name="Test Co",
            sector=Sector.CEMENT,
            years=tuple(growing_years()),
            peers=PeerStatistics(sector=Sector.CEMENT, peer_count=5, median_pe=12.0),
            reference_price=150.0,
        )
        report = build_fundamentals_report(data)
        assert [metric.key for metric in report.metrics] == [
            "revenue_growth",
            "net_margin",
            "eps_trend",
            "pe_ratio",
            "debt_to_equity",
            "dividend",
            "free_cash_flow",
        ]
        assert report.score.metrics_assessed == 7
        assert report.disclaimer.is_financial_advice is False

    def test_no_history_is_a_caller_error_not_an_empty_report(self) -> None:
        data = FundamentalsInput(
            symbol="TEST",
            company_name="Test Co",
            sector=Sector.CEMENT,
            years=(),
            peers=PeerStatistics(sector=Sector.CEMENT),
        )
        with pytest.raises(ValueError, match="No financial history"):
            build_fundamentals_report(data)

    def test_only_the_most_recent_years_are_considered(self) -> None:
        data = FundamentalsInput(
            symbol="TEST",
            company_name="Test Co",
            sector=Sector.CEMENT,
            years=tuple(growing_years(count=9)),
            peers=PeerStatistics(sector=Sector.CEMENT),
        )
        report = build_fundamentals_report(data)
        assert len(report.fiscal_years) == 5
        assert report.latest_fiscal_year == 2028
