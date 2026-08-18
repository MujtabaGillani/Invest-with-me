"""Investor profile schemas - guide section 1.

The write model enforces the guide's own rules at the boundary: a position limit
above 100% of the portfolio is not a preference, it is a mistake, and rejecting
it here means no service or UI has to defend against it later.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field, model_validator

from app.core.enums import RiskTolerance, TimeHorizon
from app.schemas.common import ReadSchema, WriteSchema


class InvestorProfileUpsert(WriteSchema):
    """Create or replace the investor's plan.

    Modelled as a full replacement (PUT) rather than a patch: this document is
    short, and the guide's instruction is to write the whole thing down before
    buying anything. A partial update would let a user quietly raise their own
    risk limit without re-reading the rest.
    """

    time_horizon: TimeHorizon
    risk_tolerance: RiskTolerance
    drawdown_tolerance_pct: Decimal = Field(
        default=Decimal("30"),
        ge=0,
        le=100,
        description="The drop you could hold through without selling in a panic.",
    )
    investable_capital: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        description="Money you can afford to have tied up or lose. Not rent or emergency funds.",
    )
    max_position_pct: Decimal = Field(
        default=Decimal("15"),
        gt=0,
        le=100,
        description="Largest share of the portfolio any single holding may take.",
    )
    max_sector_pct: Decimal = Field(
        default=Decimal("35"),
        gt=0,
        le=100,
        description="Largest share of the portfolio any single sector may take.",
    )
    emergency_fund_in_place: bool = False
    investing_borrowed_money: bool = False
    review_interval_days: int = Field(
        default=90,
        ge=7,
        le=730,
        description="How often to revisit the reason you own each holding.",
    )
    goals_note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def check_limits_are_coherent(self) -> InvestorProfileUpsert:
        """A single-position cap above the sector cap cannot be honoured.

        Every position belongs to a sector, so allowing 40% in one stock while
        capping its sector at 30% guarantees a contradiction the moment the user
        acts on their own rules. Caught here rather than surfacing later as a
        permanent, unfixable concentration warning.
        """
        if self.max_position_pct > self.max_sector_pct:
            raise ValueError(
                "max_position_pct cannot exceed max_sector_pct - a single holding cannot be "
                "allowed a larger share of the portfolio than the whole sector it belongs to."
            )
        return self


class InvestorProfileRead(ReadSchema):
    """The stored plan, plus any warnings it implies."""

    time_horizon: TimeHorizon
    risk_tolerance: RiskTolerance
    drawdown_tolerance_pct: Decimal
    investable_capital: Decimal
    max_position_pct: Decimal
    max_sector_pct: Decimal
    emergency_fund_in_place: bool
    investing_borrowed_money: bool
    review_interval_days: int
    goals_note: str | None = None

    #: Derived, never stored: things the guide would tell this user to fix.
    #: Recomputed on every read so editing the profile updates them immediately.
    warnings: list[str] = Field(default_factory=list)
