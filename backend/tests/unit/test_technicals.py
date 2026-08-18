"""Technical reading classification and framing."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.analysis.inputs import PriceBarInput, TechnicalsInput
from app.analysis.rules import DEFAULT_TECHNICAL_RULES
from app.analysis.technicals import (
    build_technical_report,
    classify_moving_averages,
    classify_rsi,
    classify_trend,
    classify_volume,
)
from app.core.enums import (
    MovingAveragePosition,
    RsiZone,
    TimeHorizon,
    TrendDirection,
    VolumeConfirmation,
)

pytestmark = pytest.mark.unit

START = date(2024, 1, 1)


def series(closes: list[float], volumes: list[int] | None = None) -> TechnicalsInput:
    """Build a price series from closes, one bar per calendar day."""
    volumes = volumes or [100_000] * len(closes)
    bars = tuple(
        PriceBarInput(
            trade_date=START + timedelta(days=index),
            open=close,
            high=close * 1.01,
            low=close * 0.99,
            close=close,
            volume=volume,
        )
        for index, (close, volume) in enumerate(zip(closes, volumes, strict=True))
    )
    return TechnicalsInput(symbol="TEST", bars=bars)


def ramp(count: int, start: float = 100.0, step: float = 0.5) -> list[float]:
    return [start + step * index for index in range(count)]


class TestClassifyTrend:
    def test_clear_rise_is_an_uptrend(self) -> None:
        direction, change = classify_trend(tuple(ramp(100)))
        assert direction is TrendDirection.UPTREND
        assert change is not None and change > 0

    def test_clear_fall_is_a_downtrend(self) -> None:
        direction, _ = classify_trend(tuple(ramp(100, start=200.0, step=-0.5)))
        assert direction is TrendDirection.DOWNTREND

    def test_small_drift_is_sideways_not_a_trend(self) -> None:
        """Without a dead band, a 0.4% wander over three months reads as a trend."""
        closes = tuple(100.0 + 0.004 * index for index in range(80))
        direction, change = classify_trend(closes)
        assert direction is TrendDirection.SIDEWAYS
        assert change is not None and abs(change) < DEFAULT_TECHNICAL_RULES.trend_flat_band_pct

    def test_single_observation_is_unknown(self) -> None:
        assert classify_trend((100.0,)) == (TrendDirection.UNKNOWN, None)


class TestClassifyRsi:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (12.0, RsiZone.OVERSOLD),
            (29.99, RsiZone.OVERSOLD),
            (30.0, RsiZone.NEUTRAL),  # boundary is exclusive
            (50.0, RsiZone.NEUTRAL),
            (70.0, RsiZone.NEUTRAL),  # boundary is exclusive
            (70.01, RsiZone.OVERBOUGHT),
            (None, RsiZone.UNKNOWN),
        ],
    )
    def test_bands(self, value: float | None, expected: RsiZone) -> None:
        assert classify_rsi(value) is expected


class TestClassifyMovingAverages:
    def test_above_both(self) -> None:
        assert classify_moving_averages(120.0, 110.0, 100.0) is MovingAveragePosition.ABOVE_BOTH

    def test_below_both(self) -> None:
        assert classify_moving_averages(90.0, 110.0, 100.0) is MovingAveragePosition.BELOW_BOTH

    def test_between_the_two_is_mixed(self) -> None:
        assert classify_moving_averages(105.0, 110.0, 100.0) is MovingAveragePosition.MIXED

    def test_missing_long_average_is_unknown_not_a_partial_judgement(self) -> None:
        """ "Above both" and "above the only one we could compute" differ."""
        assert classify_moving_averages(120.0, 110.0, None) is MovingAveragePosition.UNKNOWN


class TestClassifyVolume:
    def test_big_move_on_heavy_volume_is_confirmed(self) -> None:
        assert classify_volume(300_000, 100_000.0, 3.5) is VolumeConfirmation.CONFIRMED

    def test_big_move_on_ordinary_volume_is_unconfirmed(self) -> None:
        assert classify_volume(105_000, 100_000.0, 3.5) is VolumeConfirmation.UNCONFIRMED

    def test_a_non_move_has_nothing_to_confirm(self) -> None:
        """Confirming a 0.1% drift would imply a judgement that was never made."""
        assert classify_volume(300_000, 100_000.0, 0.1) is VolumeConfirmation.UNKNOWN

    def test_missing_average_is_unknown(self) -> None:
        assert classify_volume(300_000, None, 3.5) is VolumeConfirmation.UNKNOWN


class TestBuildTechnicalReport:
    def test_short_history_is_rejected_rather_than_half_computed(self) -> None:
        with pytest.raises(ValueError, match="at least"):
            build_technical_report(series(ramp(10)))

    def test_out_of_order_bars_are_rejected(self) -> None:
        """A mis-ordered series is a data-layer bug, and every indicator assumes order."""
        data = series(ramp(40))
        reversed_data = TechnicalsInput(symbol="TEST", bars=tuple(reversed(data.bars)))
        with pytest.raises(ValueError, match="ascending date order"):
            build_technical_report(reversed_data)

    def test_duplicate_dates_are_rejected(self) -> None:
        bars = list(series(ramp(40)).bars)
        bars[5] = PriceBarInput(
            trade_date=bars[4].trade_date,
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1,
        )
        with pytest.raises(ValueError, match="ascending date order"):
            build_technical_report(TechnicalsInput(symbol="TEST", bars=tuple(bars)))

    def test_moving_averages_are_unknown_until_enough_history_exists(self) -> None:
        """40 sessions is enough for an RSI but not for a 50-day average."""
        report = build_technical_report(series(ramp(40)))
        assert report.moving_average_position is MovingAveragePosition.UNKNOWN
        assert report.rsi.value is not None
        assert "cannot be calculated yet" in report.moving_averages.commentary

    def test_full_history_produces_every_reading(self) -> None:
        report = build_technical_report(series(ramp(260)))
        assert report.sessions_analysed == 260
        assert report.trend_direction is TrendDirection.UPTREND
        assert report.moving_average_position is MovingAveragePosition.ABOVE_BOTH
        assert report.rsi.value is not None
        assert report.as_of == START + timedelta(days=259)

    def test_horizon_note_is_framed_for_a_long_term_holder(self) -> None:
        report = build_technical_report(series(ramp(260)), horizon=TimeHorizon.LONG_TERM)
        assert "long-term" in report.horizon_note
        assert "matters far less" in report.horizon_note

    def test_horizon_note_warns_short_term_holders_about_the_difference(self) -> None:
        report = build_technical_report(series(ramp(260)), horizon=TimeHorizon.SHORT_TERM)
        assert "different skill" in report.horizon_note

    def test_report_never_recommends_an_action(self) -> None:
        """Guard against wording drift: no reading may tell the user to trade."""
        report = build_technical_report(series(ramp(260)), horizon=TimeHorizon.LONG_TERM)
        text = " ".join(
            [
                report.horizon_note,
                report.trend.commentary,
                report.rsi.commentary,
                report.moving_averages.commentary,
                report.volume.commentary,
            ]
        ).lower()
        for phrase in ("you should buy", "you should sell", "recommend", "guaranteed"):
            assert phrase not in text
