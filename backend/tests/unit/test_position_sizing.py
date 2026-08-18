"""Position sizing (guide section 5, question 5).

This is the one calculation that decides whether the app tells someone their
intended purchase is too large, so the boundary behaviour is pinned rather than
sampled.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.analysis.position_sizing import assess_position_size

pytestmark = pytest.mark.unit


def assess(
    *,
    intended: str | None = None,
    portfolio: str = "0",
    capital: str = "0",
    limit_pct: str = "15",
):
    return assess_position_size(
        intended_amount=None if intended is None else Decimal(intended),
        portfolio_value=Decimal(portfolio),
        investable_capital=Decimal(capital),
        max_position_pct=Decimal(limit_pct),
    )


class TestSizingBase:
    def test_uses_declared_capital_when_the_portfolio_is_empty(self) -> None:
        """Against portfolio value alone, a first purchase is always 100%."""
        result = assess(portfolio="0", capital="1000000", limit_pct="15")

        assert result.sizing_base == Decimal("1000000.00")
        assert result.suggested_max_amount == Decimal("150000.00")

    def test_uses_portfolio_value_once_it_exceeds_declared_capital(self) -> None:
        """Otherwise gains would be ignored as the portfolio grows."""
        result = assess(portfolio="2500000", capital="1000000", limit_pct="10")

        assert result.sizing_base == Decimal("2500000.00")
        assert result.suggested_max_amount == Decimal("250000.00")

    def test_takes_the_larger_of_the_two(self) -> None:
        assert assess(portfolio="400000", capital="1000000").sizing_base == Decimal("1000000.00")
        assert assess(portfolio="1400000", capital="1000000").sizing_base == Decimal("1400000.00")


class TestWithoutAnIntendedAmount:
    def test_reports_the_headroom_and_asks_for_an_amount(self) -> None:
        result = assess(capital="1000000", limit_pct="15")

        assert result.intended_amount is None
        assert result.exceeds_limit is None
        assert result.resulting_weight_pct is None
        assert result.suggested_max_amount == Decimal("150000.00")
        assert "Enter an intended amount" in result.commentary


class TestPostPurchaseWeight:
    def test_weight_is_measured_after_the_purchase_settles(self) -> None:
        """Measuring against the pre-purchase base would understate the result.

        150,000 into a 1,000,000 base is 15% of the *old* portfolio but only
        13.04% of the 1,150,000 the user ends up holding.
        """
        result = assess(intended="150000", capital="1000000", limit_pct="15")

        assert result.resulting_weight_pct == Decimal("13.04")
        assert result.exceeds_limit is False

    def test_a_pre_purchase_measure_would_have_waved_this_through(self) -> None:
        """230,000 is 23% of the old base but 18.7% of the resulting portfolio."""
        result = assess(intended="230000", capital="1000000", limit_pct="20")

        assert result.resulting_weight_pct == Decimal("18.70")
        assert result.exceeds_limit is False

    def test_an_oversized_purchase_is_flagged_with_a_workable_number(self) -> None:
        result = assess(intended="500000", capital="1000000", limit_pct="15")

        assert result.exceeds_limit is True
        assert result.resulting_weight_pct == Decimal("33.33")
        assert result.suggested_max_amount == Decimal("150000.00")
        assert "above the 15% single-holding limit you set" in result.commentary
        assert "diversifying limits the damage" in result.commentary

    def test_exactly_at_the_limit_is_permitted(self) -> None:
        """The limit is a ceiling the user may reach, not one they must stay under."""
        # x / (1,000,000 + x) = 0.15  ->  x = 176,470.59
        result = assess(intended="176470.58", capital="1000000", limit_pct="15")

        assert result.resulting_weight_pct == Decimal("15.00")
        assert result.exceeds_limit is False

    def test_a_fraction_over_the_limit_is_flagged(self) -> None:
        result = assess(intended="180000", capital="1000000", limit_pct="15")
        assert result.resulting_weight_pct == Decimal("15.25")
        assert result.exceeds_limit is True


class TestDegenerateInputs:
    def test_nothing_to_size_against_is_reported_honestly(self) -> None:
        """No holdings and no declared capital - no division, no invented base."""
        result = assess(intended="50000", portfolio="0", capital="0")

        assert result.exceeds_limit is None
        assert result.resulting_weight_pct is None
        assert result.sizing_base == Decimal("0.00")
        assert "nothing to size this purchase against" in result.commentary
        assert "investor profile" in result.commentary

    def test_a_100_percent_limit_permits_anything(self) -> None:
        result = assess(intended="5000000", capital="1000000", limit_pct="100")
        assert result.exceeds_limit is False

    def test_money_is_reported_to_two_decimal_places(self) -> None:
        result = assess(intended="33333.333", capital="99999.999", limit_pct="15")
        assert result.intended_amount == Decimal("33333.33")
        assert result.sizing_base == Decimal("100000.00")
        assert str(result.suggested_max_amount) == "15000.00"
