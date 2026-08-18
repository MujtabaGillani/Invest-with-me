"""Trade plan service - the pre-commitment workflow (guide sections 5 and 6).

This service owns one invariant, and it is the point of the whole product:

    **A plan cannot be committed to until all five pre-buy questions are answered
    "yes" and both exit rules are set.**

Everything else here supports that: readiness reporting so the user can see what
is missing, position sizing so question five has a real answer, and the review
journal so the commitment is revisited rather than forgotten.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.analysis.position_sizing import assess_position_size
from app.core.clock import utcnow
from app.core.enums import TradePlanStatus
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.plan_review import PlanReview
from app.models.trade_plan import TradePlan
from app.repositories.plans import TradePlanRepository
from app.schemas.common import Page
from app.schemas.plans import (
    CHECKLIST_QUESTIONS,
    ChecklistItemRead,
    PlanReviewRead,
    PositionSizingCheck,
    TradePlanCreate,
    TradePlanDetail,
    TradePlanRead,
    TradePlanReadiness,
    TradePlanReviewCreate,
    TradePlanUpdate,
)
from app.services.companies import CompanyService
from app.services.portfolio import PortfolioService
from app.services.profile import ProfileService

logger = get_logger(__name__)

#: Statuses whose plans may still be edited. Once a plan is EXECUTED its
#: checklist and exit rules are a historical record of a decision that was
#: acted on - editing them would rewrite the past and defeat the journal.
EDITABLE_STATUSES: frozenset[TradePlanStatus] = frozenset({TradePlanStatus.DRAFT})

#: A thesis shorter than this is treated as a placeholder rather than a reason.
_MIN_USEFUL_THESIS_LENGTH = 20


class TradePlanService:
    """Create, assess, commit and review trade plans."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.plans = TradePlanRepository(session)
        self.companies = CompanyService(session)
        self.profiles = ProfileService(session)
        self.portfolio = PortfolioService(session)

    # -- Reads -------------------------------------------------------------

    def list_plans(
        self,
        user_id: int,
        *,
        status: TradePlanStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[TradePlanRead]:
        """Paginated plan list, newest first.

        Position sizing is computed once for the whole page rather than per plan:
        the portfolio value it depends on is identical for every row, and
        recomputing it would replay the trade ledger once per plan.
        """
        rows, total = self.plans.search(user_id, status=status, limit=limit, offset=offset)
        sizing_base = self._sizing_context(user_id)
        items = [self._to_read_model(plan, sizing_base) for plan in rows]
        return Page[TradePlanRead](items=items, total=total, limit=limit, offset=offset)

    def get_plan(self, user_id: int, plan_id: int) -> TradePlanDetail:
        """One plan with its review journal."""
        plan = self._require_plan(user_id, plan_id)
        base = self._to_read_model(plan, self._sizing_context(user_id))
        return TradePlanDetail(
            **base.model_dump(),
            reviews=[
                PlanReviewRead(
                    id=review.id,
                    note=review.note,
                    thesis_still_valid=review.thesis_still_valid,
                    created_at=review.created_at,
                )
                for review in plan.reviews
            ],
        )

    # -- Writes ------------------------------------------------------------

    def create_plan(self, user_id: int, payload: TradePlanCreate) -> TradePlanDetail:
        """Open a draft plan for a company.

        A second *open* plan for the same company is rejected: two live plans mean
        two different stop-losses for one position, and nothing could then decide
        which one an alert should fire on. Closed and abandoned plans are left
        alone, so a user can plan the same company again later.
        """
        company = self.companies.require_company(payload.symbol)

        existing = [
            plan for plan in self.plans.list_open_for_user(user_id) if plan.company_id == company.id
        ]
        if existing:
            raise ConflictError(
                f"You already have an open plan for {company.symbol}.",
                details={"plan_id": existing[0].id, "status": existing[0].status.value},
            )

        plan = TradePlan(
            user_id=user_id,
            company_id=company.id,
            status=TradePlanStatus.DRAFT,
            thesis=payload.thesis,
            invalidation_note=payload.invalidation_note,
            intended_amount=payload.intended_amount,
            profit_target_pct=payload.profit_target_pct,
            stop_loss_pct=payload.stop_loss_pct,
        )
        self.session.add(plan)
        self.session.commit()
        self.session.refresh(plan)
        logger.info("Created trade plan %s for %s (user %s).", plan.id, company.symbol, user_id)
        return self.get_plan(user_id, plan.id)

    def update_plan(self, user_id: int, plan_id: int, payload: TradePlanUpdate) -> TradePlanDetail:
        """Patch a draft plan.

        Only fields explicitly present in the request body are applied, so
        omitting a field never clears it.
        """
        plan = self._require_plan(user_id, plan_id)
        if plan.status not in EDITABLE_STATUSES:
            raise ConflictError(
                f"A plan in '{plan.status.value}' state cannot be edited. It records a decision "
                "that has already been made.",
                details={"plan_id": plan_id, "status": plan.status.value},
            )

        for field_name in payload.model_fields_set:
            setattr(plan, field_name, getattr(payload, field_name))

        self.session.commit()
        self.session.refresh(plan)
        return self.get_plan(user_id, plan.id)

    def commit_plan(self, user_id: int, plan_id: int) -> TradePlanDetail:
        """Move a plan from DRAFT to READY.

        This is the commitment moment the guide describes: the decision is now
        written down, and the exit rules were chosen before any money was at risk.
        Refuses if the plan is not ready, listing every reason.
        """
        plan = self._require_plan(user_id, plan_id)
        if plan.status is not TradePlanStatus.DRAFT:
            raise ConflictError(
                f"Only a draft plan can be committed; this one is '{plan.status.value}'.",
                details={"plan_id": plan_id, "status": plan.status.value},
            )

        sizing = self._position_sizing(plan, self._sizing_context(user_id))
        readiness = self._build_readiness(plan, sizing)
        if not readiness.can_commit:
            raise ValidationError(
                "This plan is not ready to commit to.",
                details={"blocking_reasons": readiness.blocking_reasons},
            )

        now = utcnow()
        plan.status = TradePlanStatus.READY
        plan.committed_at = now
        plan.last_reviewed_at = now
        self.session.commit()
        self.session.refresh(plan)
        logger.info("Committed trade plan %s (user %s).", plan.id, user_id)
        return self.get_plan(user_id, plan.id)

    def abandon_plan(
        self, user_id: int, plan_id: int, *, reason: str | None = None
    ) -> TradePlanDetail:
        """Abandon a plan that was never acted on.

        Kept rather than deleted: a decision *not* to buy, and why, is part of the
        journal - and re-reading it is what stops the same idea being revisited on
        the same flimsy basis six months later.
        """
        plan = self._require_plan(user_id, plan_id)
        if plan.status not in {TradePlanStatus.DRAFT, TradePlanStatus.READY}:
            raise ConflictError(
                f"A plan in '{plan.status.value}' state cannot be abandoned.",
                details={"plan_id": plan_id, "status": plan.status.value},
            )

        plan.status = TradePlanStatus.ABANDONED
        if reason:
            self.session.add(
                PlanReview(plan_id=plan.id, note=f"Abandoned: {reason}", thesis_still_valid=False)
            )
        self.session.commit()
        return self.get_plan(user_id, plan.id)

    def close_plan(self, user_id: int, plan_id: int) -> TradePlanDetail:
        """Mark an executed plan as closed, once the position has been exited."""
        plan = self._require_plan(user_id, plan_id)
        if plan.status is not TradePlanStatus.EXECUTED:
            raise ConflictError(
                f"Only an executed plan can be closed; this one is '{plan.status.value}'.",
                details={"plan_id": plan_id, "status": plan.status.value},
            )
        plan.status = TradePlanStatus.CLOSED
        self.session.commit()
        return self.get_plan(user_id, plan.id)

    def record_review(
        self, user_id: int, plan_id: int, payload: TradePlanReviewCreate
    ) -> TradePlanDetail:
        """Record a thesis check-in.

        Allowed on READY and EXECUTED plans - the two states where the user still
        holds a live commitment. Updating ``last_reviewed_at`` is what clears the
        review-due alert, which is why the note is mandatory at the schema level.
        """
        plan = self._require_plan(user_id, plan_id)
        if plan.status not in {TradePlanStatus.READY, TradePlanStatus.EXECUTED}:
            raise ConflictError(
                f"A plan in '{plan.status.value}' state has no live thesis to review.",
                details={"plan_id": plan_id, "status": plan.status.value},
            )

        self.session.add(
            PlanReview(
                plan_id=plan.id,
                note=payload.note,
                thesis_still_valid=payload.thesis_still_valid,
            )
        )
        plan.last_reviewed_at = utcnow()
        self.session.commit()
        self.session.refresh(plan)
        return self.get_plan(user_id, plan.id)

    # -- Internals ---------------------------------------------------------

    def _require_plan(self, user_id: int, plan_id: int) -> TradePlan:
        """Fetch a plan owned by this user, or raise 404."""
        plan = self.plans.get_for_user(user_id, plan_id)
        if plan is None:
            raise NotFoundError("Trade plan not found.", details={"plan_id": plan_id})
        return plan

    def _sizing_context(self, user_id: int) -> tuple[Decimal, Decimal, Decimal]:
        """``(portfolio value, investable capital, max position %)`` for this user.

        Computed once per request and threaded through, because the portfolio value
        requires a full ledger replay.
        """
        profile = self.profiles.get_effective(user_id)
        return (
            self.portfolio.portfolio_value(user_id),
            profile.investable_capital,
            profile.max_position_pct,
        )

    @staticmethod
    def _position_sizing(
        plan: TradePlan, context: tuple[Decimal, Decimal, Decimal]
    ) -> PositionSizingCheck:
        portfolio_value, investable_capital, max_position_pct = context
        return assess_position_size(
            intended_amount=plan.intended_amount,
            portfolio_value=portfolio_value,
            investable_capital=investable_capital,
            max_position_pct=max_position_pct,
        )

    def _to_read_model(
        self, plan: TradePlan, context: tuple[Decimal, Decimal, Decimal]
    ) -> TradePlanRead:
        sizing = self._position_sizing(plan, context)
        return TradePlanRead(
            id=plan.id,
            company_id=plan.company_id,
            symbol=plan.company.symbol,
            company_name=plan.company.name,
            status=plan.status,
            checklist=[
                ChecklistItemRead(key=key, question=question, answer=plan.checklist_answers[key])
                for key, question in CHECKLIST_QUESTIONS.items()
            ],
            thesis=plan.thesis,
            invalidation_note=plan.invalidation_note,
            intended_amount=plan.intended_amount,
            profit_target_pct=plan.profit_target_pct,
            stop_loss_pct=plan.stop_loss_pct,
            committed_at=plan.committed_at,
            last_reviewed_at=plan.last_reviewed_at,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            readiness=self._build_readiness(plan, sizing),
            position_sizing=sizing,
        )

    @staticmethod
    def _build_readiness(plan: TradePlan, sizing: PositionSizingCheck) -> TradePlanReadiness:
        """Explain precisely why a plan can or cannot be committed to.

        Blocking reasons are quoted back as the guide's own questions, so the user
        sees which check they have not cleared rather than a field name.
        """
        blocking: list[str] = []
        advisory: list[str] = []

        unanswered = plan.unanswered_checklist_items
        failed = plan.failed_checklist_items

        for key in unanswered:
            blocking.append(f"Not yet answered: {CHECKLIST_QUESTIONS[key]}")
        for key in failed:
            blocking.append(f"Answered no: {CHECKLIST_QUESTIONS[key]}")

        if plan.profit_target_pct is None:
            blocking.append(
                "No profit target set. Decide before buying at what gain you would take "
                "something off the table."
            )
        if plan.stop_loss_pct is None:
            blocking.append(
                "No stop-loss set. Decide before buying how large a loss you are willing to "
                "accept, so a small one cannot quietly become a large one."
            )

        if not plan.thesis or len(plan.thesis.strip()) < _MIN_USEFUL_THESIS_LENGTH:
            advisory.append(
                "The thesis is empty or very short. If you cannot state why you are buying, "
                "you will not be able to tell later whether that reason has stopped being true."
            )
        if not plan.invalidation_note:
            advisory.append(
                "Nothing is recorded about what would prove this thesis wrong. Writing it down "
                "now, while it is hypothetical, is far easier than deciding during a loss."
            )
        if sizing.exceeds_limit:
            advisory.append(
                "The intended amount is above your own single-holding limit - see the position "
                "sizing check."
            )
        # Not a rule from the guide, so advisory only: a target smaller than the
        # stop means the plan risks more than it stands to gain.
        if (
            plan.profit_target_pct is not None
            and plan.stop_loss_pct is not None
            and plan.profit_target_pct < plan.stop_loss_pct
        ):
            advisory.append(
                f"Your profit target ({plan.profit_target_pct:g}%) is smaller than your "
                f"stop-loss ({plan.stop_loss_pct:g}%), so the plan risks more than it aims "
                "to make. That can still be deliberate - just make sure it is."
            )

        return TradePlanReadiness(
            can_commit=not blocking,
            checklist_complete=plan.checklist_complete,
            has_exit_rules=plan.has_exit_rules,
            unanswered_items=unanswered,
            failed_items=failed,
            blocking_reasons=blocking,
            advisory_notes=advisory,
        )
