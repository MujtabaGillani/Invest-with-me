"""Numeric helpers.

Every function here returns ``None`` rather than raising or inventing a number
when the maths is undefined. That is what lets the analysis engines report
"insufficient data" honestly instead of emitting a confident-looking figure, so
the ``None`` paths are the point of these tests.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.numeric import (
    cagr,
    count_positive,
    mean,
    median,
    pct_change,
    round_or_none,
    safe_div,
    stdev,
    to_float,
)

pytestmark = pytest.mark.unit


class TestSafeDiv:
    def test_divides(self) -> None:
        assert safe_div(10.0, 4.0) == pytest.approx(2.5)

    def test_a_zero_denominator_is_undefined(self) -> None:
        assert safe_div(10.0, 0.0) is None

    def test_a_missing_operand_is_undefined(self) -> None:
        assert safe_div(None, 4.0) is None
        assert safe_div(10.0, None) is None

    def test_a_negative_denominator_is_allowed_through(self) -> None:
        """Negative equity is real information, and the caller decides what it means."""
        assert safe_div(10.0, -4.0) == pytest.approx(-2.5)


class TestPctChange:
    def test_computes_a_percentage(self) -> None:
        assert pct_change(120.0, 100.0) == pytest.approx(20.0)

    def test_reports_a_decline(self) -> None:
        assert pct_change(80.0, 100.0) == pytest.approx(-20.0)

    def test_a_non_positive_base_is_refused(self) -> None:
        """ "Revenue grew 150%" is meaningless when last year was a loss."""
        assert pct_change(50.0, -100.0) is None
        assert pct_change(50.0, 0.0) is None

    def test_a_missing_operand_is_undefined(self) -> None:
        assert pct_change(None, 100.0) is None
        assert pct_change(100.0, None) is None


class TestCagr:
    def test_computes_a_compound_rate(self) -> None:
        # 100 -> 121 over two periods is 10% a year.
        assert cagr(100.0, 121.0, 2) == pytest.approx(10.0)

    def test_a_single_period_matches_simple_growth(self) -> None:
        assert cagr(100.0, 150.0, 1) == pytest.approx(50.0)

    def test_reports_decline(self) -> None:
        rate = cagr(100.0, 81.0, 2)
        assert rate is not None and rate == pytest.approx(-10.0)

    def test_non_positive_endpoints_are_refused(self) -> None:
        assert cagr(-100.0, 200.0, 3) is None
        assert cagr(100.0, -50.0, 3) is None
        assert cagr(0.0, 100.0, 3) is None

    def test_zero_periods_is_refused(self) -> None:
        assert cagr(100.0, 200.0, 0) is None


class TestAggregates:
    def test_mean_and_median_agree_on_a_symmetric_series(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert mean(values) == pytest.approx(3.0)
        assert median(values) == pytest.approx(3.0)

    def test_median_of_an_even_series_averages_the_middle_pair(self) -> None:
        assert median([1.0, 2.0, 3.0, 4.0]) == pytest.approx(2.5)

    def test_median_resists_the_outlier_a_mean_would_follow(self) -> None:
        """Why peer comparisons use the median: one silly P/E must not move it."""
        values = [10.0, 11.0, 12.0, 13.0, 400.0]
        assert median(values) == pytest.approx(12.0)
        assert mean(values) == pytest.approx(89.2)

    def test_median_does_not_mutate_its_input(self) -> None:
        values = [3.0, 1.0, 2.0]
        median(values)
        assert values == [3.0, 1.0, 2.0]

    def test_empty_series_have_no_average(self) -> None:
        assert mean([]) is None
        assert median([]) is None

    def test_stdev_needs_at_least_two_observations(self) -> None:
        assert stdev([5.0]) is None
        assert stdev([]) is None

    def test_stdev_of_a_flat_series_is_zero(self) -> None:
        assert stdev([5.0, 5.0, 5.0]) == pytest.approx(0.0)

    def test_stdev_is_the_sample_not_population_figure(self) -> None:
        # Sample stdev of 2,4,4,4,5,5,7,9 is 2.138; the population figure is 2.0.
        assert stdev([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]) == pytest.approx(2.138, abs=0.001)


class TestCountPositive:
    def test_counts_only_strictly_positive_values(self) -> None:
        assert count_positive([1.0, -1.0, 0.0, 5.0]) == 2

    def test_ignores_missing_values(self) -> None:
        assert count_positive([1.0, None, 2.0, None]) == 2

    def test_an_empty_series_counts_zero(self) -> None:
        assert count_positive([]) == 0


class TestConversions:
    def test_to_float_preserves_none(self) -> None:
        assert to_float(None) is None

    def test_to_float_converts_decimal(self) -> None:
        assert to_float(Decimal("12.34")) == pytest.approx(12.34)

    def test_round_or_none_preserves_none(self) -> None:
        assert round_or_none(None) is None

    def test_round_or_none_rounds_to_the_requested_places(self) -> None:
        assert round_or_none(12.3456, 2) == pytest.approx(12.35)
        assert round_or_none(12.3456, 0) == pytest.approx(12.0)
