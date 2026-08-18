"""Portfolio construction, valuation and concentration checks.

Holdings are **derived from the trade ledger on every read** - there is no
holdings table. The reasoning is in the module docstring of
:mod:`app.models.trade`; the replay itself is :meth:`PortfolioService.replay`.

Cost basis uses the **weighted average** method: every share held is carried at
the average price paid across all purchases. FIFO would report a different
realised profit on a partial sale, and the average-cost figure is the one a
PSX broker statement shows, so matching it means the user can reconcile the two
without arithmetic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.enums import SECTOR_LABELS, Sector, TradePlanStatus, TradeSide
from app.core.errors import CompanyNotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.company import Company
from app.models.investor_profile import InvestorProfile
from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from app.repositories.companies import CompanyRepository
from app.repositories.plans import TradePlanRepository
from app.repositories.trades import TradeRepository
from app.schemas.portfolio import (
    ConcentrationWarning,
    HoldingRead,
    PortfolioRead,
    PortfolioSummary,
    SectorAllocation,
    TradeCreate,
    TradeRead,
)
from app.services.profile import ProfileService

logger = get_logger(__name__)

_MONEY = Decimal("0.01")
_PERCENT = Decimal("0.01")
_ZERO = Decimal("0")
#: Share counts below this are treated as a fully closed position. Guards against
#: a residue like 0.0000001 shares - from a bonus-share adjustment or a rounding
#: correction - keeping a closed position visible in the portfolio for ever.
_QUANTITY_EPSILON = Decimal("0.0001")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _percent(value: Decimal) -> Decimal:
    return value.quantize(_PERCENT, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class ReplayedPosition:
    """Running state for one company while replaying its trades."""

    company_id: int
    quantity: Decimal = _ZERO
    #: Total still invested in the shares currently held, including buy fees.
    cost_basis: Decimal = _ZERO
    #: Banked profit or loss on shares already sold, net of fees on both legs.
    realised_pl: Decimal = _ZERO
    fees_paid: Decimal = _ZERO
    first_bought_at: datetime | None = None
    last_trade_at: datetime | None = None
    #: Sells that exceeded the recorded holding, kept for diagnostics.
    oversold_events: list[str] = field(default_factory=list)

    @property
    def average_cost(self) -> Decimal:
        """Cost basis per share still held, or zero for a closed position."""
        if self.quantity <= _ZERO:
            return _ZERO
        return self.cost_basis / self.quantity

    @property
    def is_open(self) -> bool:
        return self.quantity > _QUANTITY_EPSILON


class PortfolioService:
    """Build, value and assess the user's portfolio."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.trades = TradeRepository(session)
        self.plans = TradePlanRepository(session)
        self.companies = CompanyRepository(session)
        self.profiles = ProfileService(session)

    # -- Replay ------------------------------------------------------------

    def replay(self, user_id: int) -> dict[int, ReplayedPosition]:
        """Rebuild every position from the trade ledger.

        Returns *all* companies ever traded, including fully closed positions, so
        realised profit is not lost from the summary when a position is exited.

        A sell larger than the recorded holding is clamped rather than rejected:
        by the time a bad row is in the ledger, refusing to compute the portfolio
        would lock the user out of the whole screen. It is logged and reported on
        the position so it can be corrected.
        """
        positions: dict[int, ReplayedPosition] = {}

        for trade in self.trades.list_for_user(user_id):
            position = positions.setdefault(
                trade.company_id, ReplayedPosition(company_id=trade.company_id)
            )
            position.fees_paid += trade.fees
            position.last_trade_at = trade.executed_at

            if trade.side is TradeSide.BUY:
                if position.first_bought_at is None:
                    position.first_bought_at = trade.executed_at
                position.quantity += trade.quantity
                position.cost_basis += trade.gross_value + trade.fees
                continue

            # -- Sell ---------------------------------------------------------
            sold = trade.quantity
            if sold > position.quantity:
                position.oversold_events.append(
                    f"Trade {trade.id} sold {sold} shares against a recorded holding of "
                    f"{position.quantity}."
                )
                logger.warning(
                    "User %s trade %s sells more than held (%s > %s); clamping.",
                    user_id,
                    trade.id,
                    sold,
                    position.quantity,
                )
                sold = position.quantity

            if sold <= _ZERO:
                # Nothing held to sell - the trade contributes only its fees.
                position.realised_pl -= trade.fees
                continue

            cost_of_sold = position.average_cost * sold
            proceeds = sold * trade.price - trade.fees
            position.realised_pl += proceeds - cost_of_sold
            position.cost_basis -= cost_of_sold
            position.quantity -= sold

            if not position.is_open:
                # Fully closed: clear the residue so a rounding tail cannot show
                # as a phantom holding worth a fraction of a rupee.
                position.quantity = _ZERO
                position.cost_basis = _ZERO

        return positions

    def portfolio_value(self, user_id: int) -> Decimal:
        """Total market value of open holdings, for position sizing.

        Falls back to cost basis for a holding with no stored price: reporting a
        held position as worth zero would understate the portfolio and make every
        sizing check pass.
        """
        positions = self.replay(user_id)
        open_positions = [position for position in positions.values() if position.is_open]
        if not open_positions:
            return _ZERO

        prices = self.companies.latest_price_by_company(
            [position.company_id for position in open_positions]
        )
        total = _ZERO
        for position in open_positions:
            price_bar = prices.get(position.company_id)
            if price_bar is None:
                total += position.cost_basis
            else:
                total += position.quantity * price_bar.close
        return _money(total)

    # -- Presentation ------------------------------------------------------

    def get_portfolio(
        self, user_id: int, *, market_data_is_synthetic: bool = False
    ) -> PortfolioRead:
        """Everything the portfolio screen needs, in one pass over the ledger."""
        positions = self.replay(user_id)
        profile = self.profiles.get_effective(user_id)

        company_ids = list(positions)
        companies = self.companies.get_many(company_ids)
        prices = self.companies.latest_price_by_company(company_ids)
        plans_by_company = self.plans.active_plans_by_company(user_id)

        open_positions = [position for position in positions.values() if position.is_open]

        # Total market value first: every weight percentage depends on it.
        total_market_value = _ZERO
        for position in open_positions:
            price_bar = prices.get(position.company_id)
            total_market_value += (
                position.quantity * price_bar.close if price_bar else position.cost_basis
            )

        holdings = [
            self._build_holding(
                position=position,
                company=companies[position.company_id],
                last_price=(
                    prices[position.company_id].close if position.company_id in prices else None
                ),
                last_price_date=(
                    prices[position.company_id].trade_date
                    if position.company_id in prices
                    else None
                ),
                plan=plans_by_company.get(position.company_id),
                total_market_value=total_market_value,
            )
            for position in open_positions
            if position.company_id in companies
        ]
        holdings.sort(key=lambda holding: holding.market_value or _ZERO, reverse=True)

        allocations = self._build_allocations(holdings, total_market_value, profile)
        warnings = self._build_concentration_warnings(holdings, allocations, profile)
        summary = self._build_summary(positions.values(), holdings, total_market_value, allocations)

        valued_at = utcnow() if holdings else None
        return PortfolioRead(
            summary=summary,
            holdings=holdings,
            sector_allocations=allocations,
            concentration_warnings=warnings,
            valued_at=valued_at,
            market_data_is_synthetic=market_data_is_synthetic,
        )

    def _build_holding(
        self,
        *,
        position: ReplayedPosition,
        company: Company,
        last_price: Decimal | None,
        last_price_date: date | None,
        plan: TradePlan | None,
        total_market_value: Decimal,
    ) -> HoldingRead:
        """Assemble one holding row, including its pre-committed exit levels."""
        average_cost = position.average_cost
        market_value = position.quantity * last_price if last_price is not None else None
        unrealised = market_value - position.cost_basis if market_value is not None else None
        unrealised_pct = (
            _percent(unrealised / position.cost_basis * Decimal(100))
            if unrealised is not None and position.cost_basis > _ZERO
            else None
        )
        weight = (
            _percent(market_value / total_market_value * Decimal(100))
            if market_value is not None and total_market_value > _ZERO
            else None
        )

        # Exit levels are anchored to *average cost*, i.e. "what I paid", which is
        # how the guide phrases both rules ("up 20-25%", "15% below what I paid").
        target_price = (
            _money(average_cost * (Decimal(100) + plan.profit_target_pct) / Decimal(100))
            if plan is not None and plan.profit_target_pct is not None and average_cost > _ZERO
            else None
        )
        stop_price = (
            _money(average_cost * (Decimal(100) - plan.stop_loss_pct) / Decimal(100))
            if plan is not None and plan.stop_loss_pct is not None and average_cost > _ZERO
            else None
        )
        distance_to_target = (
            _percent((target_price - last_price) / last_price * Decimal(100))
            if target_price is not None and last_price and last_price > _ZERO
            else None
        )
        distance_to_stop = (
            _percent((last_price - stop_price) / last_price * Decimal(100))
            if stop_price is not None and last_price and last_price > _ZERO
            else None
        )

        return HoldingRead(
            company_id=company.id,
            symbol=company.symbol,
            company_name=company.name,
            sector=company.sector,
            sector_label=SECTOR_LABELS[company.sector],
            quantity=position.quantity,
            average_cost=_money(average_cost),
            cost_basis=_money(position.cost_basis),
            last_price=last_price,
            last_price_date=last_price_date,
            market_value=_money(market_value) if market_value is not None else None,
            unrealised_pl=_money(unrealised) if unrealised is not None else None,
            unrealised_pl_pct=unrealised_pct,
            realised_pl=_money(position.realised_pl),
            weight_pct=weight,
            plan_id=plan.id if plan else None,
            profit_target_price=target_price,
            stop_loss_price=stop_price,
            distance_to_target_pct=distance_to_target,
            distance_to_stop_pct=distance_to_stop,
            missing_exit_rules=plan is None or not plan.has_exit_rules,
            last_reviewed_at=plan.last_reviewed_at if plan else None,
        )

    def _build_allocations(
        self,
        holdings: Sequence[HoldingRead],
        total_market_value: Decimal,
        profile: InvestorProfile,
    ) -> list[SectorAllocation]:
        """Group holdings by sector and flag sectors over the user's limit."""
        totals: dict[Sector, Decimal] = {}
        counts: dict[Sector, int] = {}
        for holding in holdings:
            value = holding.market_value or holding.cost_basis
            totals[holding.sector] = totals.get(holding.sector, _ZERO) + value
            counts[holding.sector] = counts.get(holding.sector, 0) + 1

        allocations: list[SectorAllocation] = []
        for sector, value in totals.items():
            weight = (
                _percent(value / total_market_value * Decimal(100))
                if total_market_value > _ZERO
                else _ZERO
            )
            allocations.append(
                SectorAllocation(
                    sector=sector,
                    sector_label=SECTOR_LABELS[sector],
                    market_value=_money(value),
                    weight_pct=weight,
                    holdings_count=counts[sector],
                    exceeds_limit=weight > profile.max_sector_pct,
                )
            )
        allocations.sort(key=lambda allocation: allocation.weight_pct, reverse=True)
        return allocations

    def _build_concentration_warnings(
        self,
        holdings: Sequence[HoldingRead],
        allocations: Sequence[SectorAllocation],
        profile: InvestorProfile,
    ) -> list[ConcentrationWarning]:
        """Report breaches of the user's own position and sector limits."""
        warnings: list[ConcentrationWarning] = []

        for holding in holdings:
            if holding.weight_pct is not None and holding.weight_pct > profile.max_position_pct:
                warnings.append(
                    ConcentrationWarning(
                        kind="position",
                        subject=holding.symbol,
                        weight_pct=holding.weight_pct,
                        limit_pct=profile.max_position_pct,
                        message=(
                            f"{holding.symbol} is {holding.weight_pct:g}% of your portfolio, "
                            f"above the {profile.max_position_pct:g}% single-holding limit you "
                            "set. Trimming a position that has grown too large is risk "
                            "management, not an admission of a mistake."
                        ),
                    )
                )

        for allocation in allocations:
            if allocation.exceeds_limit:
                warnings.append(
                    ConcentrationWarning(
                        kind="sector",
                        subject=allocation.sector_label,
                        weight_pct=allocation.weight_pct,
                        limit_pct=profile.max_sector_pct,
                        message=(
                            f"{allocation.sector_label} is {allocation.weight_pct:g}% of your "
                            f"portfolio, above your {profile.max_sector_pct:g}% sector limit. "
                            "Companies in one sector tend to fall together."
                        ),
                    )
                )

        return warnings

    def _build_summary(
        self,
        all_positions: Sequence[ReplayedPosition],
        holdings: Sequence[HoldingRead],
        total_market_value: Decimal,
        allocations: Sequence[SectorAllocation],
    ) -> PortfolioSummary:
        """Aggregate the portfolio, including realised results from closed positions."""
        total_cost = sum((holding.cost_basis for holding in holdings), _ZERO)
        total_unrealised = sum(
            (holding.unrealised_pl for holding in holdings if holding.unrealised_pl is not None),
            _ZERO,
        )
        # Realised profit spans every position ever held, not just open ones.
        total_realised = sum((position.realised_pl for position in all_positions), _ZERO)
        total_fees = sum((position.fees_paid for position in all_positions), _ZERO)
        without_rules = sum(1 for holding in holdings if holding.missing_exit_rules)

        return PortfolioSummary(
            holdings_count=len(holdings),
            sectors_held=len(allocations),
            total_cost_basis=_money(total_cost),
            total_market_value=_money(total_market_value),
            total_unrealised_pl=_money(total_unrealised),
            total_unrealised_pl_pct=(
                _percent(total_unrealised / total_cost * Decimal(100))
                if total_cost > _ZERO
                else None
            ),
            total_realised_pl=_money(total_realised),
            total_fees_paid=_money(total_fees),
            holdings_without_exit_rules=without_rules,
            diversification_note=self._diversification_note(holdings, allocations),
        )

    @staticmethod
    def _diversification_note(
        holdings: Sequence[HoldingRead], allocations: Sequence[SectorAllocation]
    ) -> str:
        """Describe how spread the portfolio is, without prescribing a target."""
        if not holdings:
            return "No open holdings yet."
        if len(holdings) == 1:
            return (
                "Your entire portfolio is one company. Whatever happens to it happens to all of "
                "your invested money."
            )
        largest = max((allocation.weight_pct for allocation in allocations), default=Decimal("0"))
        base = (
            f"{len(holdings)} holdings across {len(allocations)} "
            f"{'sector' if len(allocations) == 1 else 'sectors'}."
        )
        if len(allocations) == 1:
            return (
                base + " Everything you own is exposed to the same sector, so a sector-wide "
                "shock hits all of it at once."
            )
        if largest >= Decimal("60"):
            return base + f" The largest sector is {largest:g}% of the portfolio."
        return base + " Spread across several sectors, which limits what any one of them can do."

    # -- Trades ------------------------------------------------------------

    def list_trades(self, user_id: int, *, limit: int = 50) -> list[TradeRead]:
        """Recent trades, newest first."""
        rows = self.trades.list_recent_for_user(user_id, limit=limit)
        return [self._to_trade_read(trade) for trade in rows]

    def record_trade(self, user_id: int, payload: TradeCreate) -> TradeRead:
        """Append a trade to the ledger.

        A sell larger than the current holding is rejected here - at the point of
        entry, where the user can still correct it - rather than being tolerated by
        the replay. Validating on the way in is what keeps the ledger trustworthy;
        the replay's clamping exists only for rows that predate this check or were
        loaded by a script.

        Commits, and returns the stored trade.
        """
        company = self.companies.get_by_symbol(payload.symbol)
        if company is None:
            raise CompanyNotFoundError(payload.symbol)

        executed_at = payload.executed_at or utcnow()

        if payload.side is TradeSide.SELL:
            held = self.replay(user_id).get(company.id)
            available = held.quantity if held else _ZERO
            if payload.quantity > available:
                raise ValidationError(
                    f"You hold {available:g} shares of {company.symbol}; the trade sells "
                    f"{payload.quantity:g}.",
                    details={
                        "symbol": company.symbol,
                        "quantity_held": str(available),
                        "quantity_sold": str(payload.quantity),
                    },
                )

        plan = self._resolve_plan(user_id, company.id, payload.plan_id, payload.side)

        trade = Trade(
            user_id=user_id,
            company_id=company.id,
            plan_id=plan.id if plan else None,
            side=payload.side,
            quantity=payload.quantity,
            price=payload.price,
            fees=payload.fees,
            executed_at=executed_at,
            note=payload.note,
        )
        self.session.add(trade)

        # A buy against a READY plan marks that plan as executed: the commitment
        # has been acted on, and its exit rules now govern real money.
        if (
            plan is not None
            and payload.side is TradeSide.BUY
            and plan.status is TradePlanStatus.READY
        ):
            plan.status = TradePlanStatus.EXECUTED
            plan.last_reviewed_at = plan.last_reviewed_at or executed_at

        self.session.commit()
        self.session.refresh(trade)
        return self._to_trade_read(trade)

    def _resolve_plan(
        self, user_id: int, company_id: int, plan_id: int | None, side: TradeSide
    ) -> TradePlan | None:
        """Find the plan a trade belongs to.

        An explicit ``plan_id`` is validated against the owner and the company. If
        none is given on a buy, a READY plan for that company is adopted
        automatically - the user already wrote the commitment down, and making
        them re-link it by hand would leave real positions looking unplanned.
        """
        if plan_id is not None:
            plan = self.plans.get_for_user(user_id, plan_id)
            if plan is None:
                raise ValidationError(
                    "The referenced trade plan does not exist.", details={"plan_id": plan_id}
                )
            if plan.company_id != company_id:
                raise ValidationError(
                    "The referenced trade plan is for a different company.",
                    details={"plan_id": plan_id},
                )
            return plan

        if side is TradeSide.BUY:
            return self.plans.find_committable_plan(user_id, company_id)
        return None

    @staticmethod
    def _to_trade_read(trade: Trade) -> TradeRead:
        return TradeRead(
            id=trade.id,
            symbol=trade.company.symbol,
            company_name=trade.company.name,
            side=trade.side,
            quantity=trade.quantity,
            price=trade.price,
            fees=trade.fees,
            gross_value=_money(trade.gross_value),
            net_cash_flow=_money(trade.cash_flow),
            executed_at=trade.executed_at,
            plan_id=trade.plan_id,
            note=trade.note,
        )
