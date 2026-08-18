"""Position sizing (guide section 5, question 5).

"Is this purchase small enough that it doesn't dominate my overall portfolio?"

Pure ``Decimal`` arithmetic against the limits the user set in their own profile.
No ORM, no session - so the rule can be unit-tested directly, which matters
because it is the one calculation that decides whether the app tells someone
their intended purchase is too large.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.schemas.plans import PositionSizingCheck

_MONEY = Decimal("0.01")
_PERCENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _percent(value: Decimal) -> Decimal:
    return value.quantize(_PERCENT, rounding=ROUND_HALF_UP)


def assess_position_size(
    *,
    intended_amount: Decimal | None,
    portfolio_value: Decimal,
    investable_capital: Decimal,
    max_position_pct: Decimal,
) -> PositionSizingCheck:
    """Check an intended purchase against the user's single-position limit.

    The limit is applied to the **larger** of current portfolio value and declared
    investable capital. Using portfolio value alone would make the first purchase
    in an empty portfolio infinitely oversized (any amount is 100% of nothing);
    using capital alone would ignore gains once the portfolio has grown past what
    was originally set aside. Taking the larger of the two is the only version
    that behaves sensibly at both ends.

    A purchase is measured as a share of the portfolio *after* it settles -
    ``amount / (base + amount)`` - because that is the weight the user will
    actually be carrying. Measuring against the pre-purchase base would let a
    15% limit wave through a position that ends up at 23% of the portfolio.
    """
    base = max(portfolio_value, investable_capital)
    suggested_max = _money(base * max_position_pct / Decimal(100))

    if intended_amount is None:
        return PositionSizingCheck(
            intended_amount=None,
            portfolio_value=_money(portfolio_value),
            sizing_base=_money(base),
            max_position_pct=max_position_pct,
            suggested_max_amount=suggested_max,
            exceeds_limit=None,
            resulting_weight_pct=None,
            commentary=(
                f"Your own limit of {max_position_pct:g}% of a "
                f"PKR {_money(base):,} base allows up to PKR {suggested_max:,} in any single "
                "holding. Enter an intended amount to check a specific purchase against it."
            ),
        )

    if base <= 0:
        # Nothing to size against: no holdings and no declared capital. Report it
        # honestly rather than inventing a base or dividing by zero.
        return PositionSizingCheck(
            intended_amount=_money(intended_amount),
            portfolio_value=_money(portfolio_value),
            sizing_base=Decimal("0.00"),
            max_position_pct=max_position_pct,
            suggested_max_amount=Decimal("0.00"),
            exceeds_limit=None,
            resulting_weight_pct=None,
            commentary=(
                "Your portfolio is empty and no investable capital is recorded, so there is "
                "nothing to size this purchase against. Set your investable capital in your "
                "investor profile first."
            ),
        )

    resulting_base = base + intended_amount
    resulting_weight = _percent(intended_amount / resulting_base * Decimal(100))
    exceeds = resulting_weight > max_position_pct

    if exceeds:
        commentary = (
            f"At PKR {_money(intended_amount):,} this position would be {resulting_weight:g}% of "
            f"your portfolio, above the {max_position_pct:g}% single-holding limit you set. "
            f"Around PKR {suggested_max:,} would keep you inside it. The guide's point is that "
            "diversifying limits the damage any one bad pick can do."
        )
    else:
        commentary = (
            f"At PKR {_money(intended_amount):,} this position would be {resulting_weight:g}% of "
            f"your portfolio, inside the {max_position_pct:g}% single-holding limit you set."
        )

    return PositionSizingCheck(
        intended_amount=_money(intended_amount),
        portfolio_value=_money(portfolio_value),
        sizing_base=_money(base),
        max_position_pct=max_position_pct,
        suggested_max_amount=suggested_max,
        exceeds_limit=exceeds,
        resulting_weight_pct=resulting_weight,
        commentary=commentary,
    )
