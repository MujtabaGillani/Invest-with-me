"""Trade plan schemas - guide sections 5 and 6."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator

from app.core.enums import TradePlanStatus
from app.schemas.common import ReadSchema, WriteSchema

#: Human-readable text for each pre-buy question, keyed by the field name used in
#: the ORM model and the API. Held server-side so the wording of the checklist
#: cannot drift between the API docs and the UI.
CHECKLIST_QUESTIONS: dict[str, str] = {
    "understands_business": (
        "Does the business make sense to me - do I understand what it does and how it makes money?"
    ),
    "revenue_and_profit_healthy": (
        "Are revenue and profit trending in a healthy direction over the last 3+ years?"
    ),
    "debt_manageable_vs_peers": "Is debt manageable relative to peers in the same sector?",
    "comfortable_with_drawdown": (
        "Am I comfortable holding this for my intended time horizon even if it drops 20-30% first?"
    ),
    "position_size_appropriate": (
        "Is this purchase small enough that it does not dominate my overall portfolio?"
    ),
}


class ChecklistItemRead(ReadSchema):
    """One pre-buy question and the user's answer."""

    key: str
    question: str
    answer: bool | None = Field(
        default=None, description="Null means unanswered, which is not the same as 'no'."
    )


class PositionSizingCheck(ReadSchema):
    """Whether the intended purchase respects the user's own position limit."""

    intended_amount: Decimal | None = None
    portfolio_value: Decimal = Field(
        description="Current market value of holdings, used as the sizing base."
    )
    sizing_base: Decimal = Field(
        description=(
            "The base the limit was applied to: the larger of portfolio value and declared "
            "investable capital, so the first purchase in an empty portfolio is still sized "
            "against a real number."
        )
    )
    max_position_pct: Decimal
    suggested_max_amount: Decimal
    #: Null when no intended amount has been entered yet.
    exceeds_limit: bool | None = None
    resulting_weight_pct: Decimal | None = None
    commentary: str


class TradePlanReadiness(ReadSchema):
    """Why a plan can or cannot be committed to.

    Presented as explicit blocking reasons rather than a single boolean so the UI
    can tell the user exactly what is missing instead of greying out a button.
    """

    can_commit: bool
    checklist_complete: bool
    has_exit_rules: bool
    unanswered_items: list[str] = Field(default_factory=list)
    failed_items: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    advisory_notes: list[str] = Field(
        default_factory=list,
        description="Concerns that do not block committing, e.g. a thin invalidation note.",
    )


class TradePlanRead(ReadSchema):
    """A plan, with everything the UI needs to render and act on it."""

    id: int
    company_id: int
    symbol: str
    company_name: str
    status: TradePlanStatus

    checklist: list[ChecklistItemRead]
    thesis: str | None = None
    invalidation_note: str | None = None

    intended_amount: Decimal | None = None
    profit_target_pct: Decimal | None = None
    stop_loss_pct: Decimal | None = None

    committed_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    readiness: TradePlanReadiness
    position_sizing: PositionSizingCheck | None = None


class PlanReviewRead(ReadSchema):
    """One recorded thesis check-in."""

    id: int
    note: str
    thesis_still_valid: bool
    created_at: datetime


class TradePlanDetail(TradePlanRead):
    """A single plan, including its review journal.

    Separate from :class:`TradePlanRead` so the list endpoint does not load every
    plan's full review history just to render a table.
    """

    reviews: list[PlanReviewRead] = Field(default_factory=list)


class TradePlanCreate(WriteSchema):
    """Start a plan for a company.

    Only the symbol is required: the guide's flow is to open a plan and work
    through the checklist, so demanding a complete plan up front would push users
    into filling it in somewhere else and pasting the result.
    """

    symbol: str = Field(min_length=1, max_length=16)
    thesis: str | None = Field(default=None, max_length=4000)
    invalidation_note: str | None = Field(default=None, max_length=4000)
    intended_amount: Decimal | None = Field(default=None, gt=0)
    profit_target_pct: Decimal | None = Field(default=None, gt=0, le=1000)
    stop_loss_pct: Decimal | None = Field(default=None, gt=0, lt=100)


class TradePlanUpdate(WriteSchema):
    """Patch a draft plan.

    Every field is optional, and ``None`` means "not supplied" rather than "clear
    it". Clearing an exit rule that has already been committed to is exactly the
    in-the-moment decision the guide warns against, so it is not offered as a
    side effect of an edit.
    """

    thesis: str | None = Field(default=None, max_length=4000)
    invalidation_note: str | None = Field(default=None, max_length=4000)
    intended_amount: Decimal | None = Field(default=None, gt=0)
    profit_target_pct: Decimal | None = Field(default=None, gt=0, le=1000)
    stop_loss_pct: Decimal | None = Field(default=None, gt=0, lt=100)

    understands_business: bool | None = None
    revenue_and_profit_healthy: bool | None = None
    debt_manageable_vs_peers: bool | None = None
    comfortable_with_drawdown: bool | None = None
    position_size_appropriate: bool | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> TradePlanUpdate:
        """Reject an empty patch, which is always a client bug."""
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self


class TradePlanReviewCreate(WriteSchema):
    """Record a thesis check-in (guide section 6).

    The note is mandatory. A review that records only a timestamp silences the
    THESIS_REVIEW_DUE alert without the user having actually re-examined
    anything, which would make the alert worse than useless.
    """

    note: str = Field(
        min_length=10,
        max_length=4000,
        description="What you re-checked, and whether the original reason to own it still holds.",
    )
    #: Set when the review concludes the thesis has broken. Does not sell
    #: anything - it records the conclusion and raises its own alert.
    thesis_still_valid: bool = True
