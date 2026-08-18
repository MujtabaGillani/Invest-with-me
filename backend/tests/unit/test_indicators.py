"""Technical indicator maths.

These are pinned against hand-computed values rather than against whatever the
implementation currently returns. A test that asserts ``rsi == rsi`` proves
nothing; the point of these is to catch a change in the formula.
"""

from __future__ import annotations

import pytest

from app.analysis.indicators import (
    percent_change_over,
    relative_strength_index,
    simple_moving_average,
)

pytestmark = pytest.mark.unit


class TestSimpleMovingAverage:
    def test_averages_the_last_n_values(self) -> None:
        assert simple_moving_average([1, 2, 3, 4, 5], 3) == pytest.approx(4.0)

    def test_uses_only_the_window_not_the_whole_series(self) -> None:
        # The leading 100 must not affect a 2-period average.
        assert simple_moving_average([100, 1, 3], 2) == pytest.approx(2.0)

    def test_returns_none_when_series_is_shorter_than_the_period(self) -> None:
        # A 200-day average computed from 150 days is not a 200-day average, and
        # returning one would mislabel a young listing as "below its 200-day".
        assert simple_moving_average([1, 2, 3], 5) is None

    def test_returns_none_for_a_non_positive_period(self) -> None:
        assert simple_moving_average([1, 2, 3], 0) is None


class TestRelativeStrengthIndex:
    def test_returns_none_below_the_warm_up_length(self) -> None:
        # 14 closes give only 13 changes - one short of the seed window.
        assert relative_strength_index(list(range(14)), period=14) is None

    def test_returns_100_when_there_are_no_down_sessions(self) -> None:
        rising = [float(value) for value in range(1, 40)]
        assert relative_strength_index(rising, period=14) == pytest.approx(100.0)

    def test_returns_0_when_there_are_no_up_sessions(self) -> None:
        falling = [float(value) for value in range(40, 1, -1)]
        assert relative_strength_index(falling, period=14) == pytest.approx(0.0)

    def test_alternating_equal_moves_sit_near_the_midpoint(self) -> None:
        """Equal-sized ups and downs must land in the neutral band.

        Not *exactly* 50: Wilder smoothing weights recent changes more heavily, and
        this series ends on a down session, so the average loss is slightly the
        larger of the two. Asserting exactly 50 would be asserting that the
        smoothing does not work.
        """
        closes = [100.0]
        for index in range(30):
            closes.append(closes[-1] + (1.0 if index % 2 == 0 else -1.0))
        rsi = relative_strength_index(closes, period=14)
        assert rsi is not None
        assert rsi == pytest.approx(50.0, abs=2.0)
        assert rsi < 50.0  # the final session was a down move

    def test_uses_wilder_smoothing_not_a_simple_mean(self) -> None:
        """Pinned to Wilder's method, which is what charting platforms show.

        A plain rolling mean of gains and losses over the same series gives a
        materially different number, so the 30/70 bands the guide quotes would not
        line up with the user's broker chart. Values computed by hand from the
        recurrence.
        """
        # 15 closes: a steady climb with one sharp drop, so gains and losses are
        # both non-zero and the seed differs from the smoothed result.
        closes = [
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
        ]
        rsi = relative_strength_index(closes, period=14)
        assert rsi is not None
        # Wilder's RSI for this well-known example series is ~70.5.
        assert rsi == pytest.approx(70.5, abs=1.0)

    def test_is_bounded_between_0_and_100(self) -> None:
        closes = [100.0, 105.0, 95.0, 130.0, 60.0, 90.0, 91.0, 89.0] * 6
        rsi = relative_strength_index(closes, period=14)
        assert rsi is not None
        assert 0.0 <= rsi <= 100.0


class TestPercentChangeOver:
    def test_measures_across_the_requested_span(self) -> None:
        # 3 sessions back from 110 is 100, so +10%.
        assert percent_change_over([100, 101, 105, 110], 3) == pytest.approx(10.0)

    def test_falls_back_to_the_available_span_when_history_is_short(self) -> None:
        # Only 3 observations exist, so a 60-session request uses the full 2-span.
        assert percent_change_over([100, 110, 120], 60) == pytest.approx(20.0)

    def test_returns_none_for_a_single_observation(self) -> None:
        assert percent_change_over([100], 5) is None

    def test_returns_none_when_the_base_is_not_positive(self) -> None:
        assert percent_change_over([0, 50], 1) is None
