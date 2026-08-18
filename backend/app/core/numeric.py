"""Small numeric helpers shared by the analysis engines.

Financial inputs are routinely missing, zero, or negative in ways that make the
textbook formula undefined (a P/E ratio on a loss-making company, growth from a
negative base). Every helper here returns ``None`` instead of raising or
inventing a number, so callers can report "insufficient data" honestly.

Money is handled as :class:`~decimal.Decimal` at the persistence and reporting
boundary; ratios and percentages are plain ``float`` because they are always
rounded for display and never summed into a balance.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal


def to_float(value: Decimal | float | int | None) -> float | None:
    """Coerce a possibly-``None`` numeric to ``float``."""
    if value is None:
        return None
    return float(value)


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    """Divide, returning ``None`` for undefined results.

    Undefined here means: a missing operand, or a denominator of zero. A
    *negative* denominator is allowed through - callers such as the P/E and
    debt-to-equity calculations decide for themselves whether a negative result
    is meaningful, because "negative equity" is real information, not an error.
    """
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def pct_change(current: float | None, previous: float | None) -> float | None:
    """Percentage change from ``previous`` to ``current``.

    Returns ``None`` when the base is missing, zero, or negative: "revenue grew
    150%" is meaningless when last year's figure was a loss, and reporting it
    would flatter a recovering company.
    """
    if current is None or previous is None or previous <= 0:
        return None
    return (current - previous) / previous * 100.0


def cagr(first: float | None, last: float | None, periods: int) -> float | None:
    """Compound annual growth rate, in percent, over ``periods`` intervals.

    ``periods`` is the number of *intervals*, i.e. ``len(series) - 1``. Requires
    both endpoints to be positive, for the same reason as :func:`pct_change`.
    """
    if first is None or last is None or periods <= 0 or first <= 0 or last <= 0:
        return None
    return (math.pow(last / first, 1.0 / periods) - 1.0) * 100.0


def mean(values: Sequence[float]) -> float | None:
    """Arithmetic mean, or ``None`` for an empty sequence."""
    if not values:
        return None
    return sum(values) / len(values)


def median(values: Sequence[float]) -> float | None:
    """Median, or ``None`` for an empty sequence.

    Used for peer (sector) comparisons: a single outlier P/E should not drag the
    benchmark the way a mean would.
    """
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def stdev(values: Sequence[float]) -> float | None:
    """Sample standard deviation; ``None`` for fewer than two observations."""
    if len(values) < 2:
        return None
    avg = sum(values) / len(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def round_or_none(value: float | None, digits: int = 2) -> float | None:
    """Round for presentation while preserving ``None``."""
    if value is None:
        return None
    return round(value, digits)


def count_positive(values: Sequence[float | None]) -> int:
    """Number of strictly positive observations, ignoring ``None``."""
    return sum(1 for value in values if value is not None and value > 0)
