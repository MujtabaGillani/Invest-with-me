"""Invested-versus-value over time, for the profit/loss chart.

Answers "how much have I put in, and how much is it worth" as a series rather than
a single number, by walking the trade ledger forward one day at a time and valuing
each day's holdings at that day's stored close.

**Why this is computed and not stored.** Nothing derived is persisted in this
codebase (ARCHITECTURE §5), and a portfolio-value table would be the worst possible
exception: it would silently disagree with the ledger the moment a trade was
corrected or a price was re-synced. Recomputing is cheap - the whole series is one
pass over trades and one pass over price bars.

**Forward-fill, and why it is honest here.** PSX is closed at weekends and on public
holidays, and a thinly traded company can go days without a bar. Those days carry
the previous close forward, which is what the position was actually worth: no trade
occurred, so no revaluation occurred either. The alternative - dropping the day -
would make the chart's x-axis lie about elapsed time, and interpolating would invent
prices that never traded.

Cost basis follows the same convention as
:meth:`app.services.portfolio.PortfolioService.replay`, including reducing the basis
proportionally on a sell, so the final point of this series agrees with the
portfolio screen. That agreement is asserted by a test; two different answers to
"how much have I invested" on two screens would be worse than either being absent.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.enums import TradeSide
from app.core.logging import get_logger
from app.models.trade import Trade
from app.repositories.companies import CompanyRepository
from app.repositories.trades import TradeRepository
from app.schemas.screener import PortfolioHistoryRead, PortfolioValuePoint

logger = get_logger(__name__)

_ZERO = Decimal(0)
_MONEY = Decimal("0.01")
_PERCENT = Decimal("0.01")

#: Hard ceiling on how many daily points one response will carry.
#:
#: Roughly four years of trading days. A chart cannot usefully render more, and an
#: unbounded series would grow without limit for a long-running ledger. When the
#: history is longer than this the *oldest* points are dropped, because the recent
#: shape is what the screen is for - and ``first_trade_on`` still reports the true
#: start so the truncation is visible rather than implied.
MAX_POINTS = 1000


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


class PortfolioHistoryService:
    """Reconstructs the invested/value series from the ledger. Read-only."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.trades = TradeRepository(session)
        self.companies = CompanyRepository(session)

    def history(self, user_id: int) -> PortfolioHistoryRead:
        """Daily invested, market value and profit, oldest first."""
        trades = list(self.trades.list_for_user(user_id))
        if not trades:
            return PortfolioHistoryRead(
                points=[],
                total_invested=_ZERO,
                total_market_value=_ZERO,
                total_profit=_ZERO,
                realised_profit=_ZERO,
                first_trade_on=None,
                as_of=utcnow(),
            )

        closes_by_company = self._closes(sorted({trade.company_id for trade in trades}))

        # Trades grouped by the calendar day they executed, so the walk applies a
        # day's trades before valuing that day.
        trades_by_day: dict[date, list[Trade]] = defaultdict(list)
        for trade in trades:
            trades_by_day[trade.executed_at.date()].append(trade)

        first_day = min(trades_by_day)
        last_day = max([first_day, *(max(c) for c in closes_by_company.values() if c)])
        today = utcnow().date()
        if last_day > today:
            # A stored bar dated in the future would otherwise extend the chart
            # past today. Trust the clock over the data.
            last_day = today

        quantities: dict[int, Decimal] = defaultdict(lambda: _ZERO)
        cost_bases: dict[int, Decimal] = defaultdict(lambda: _ZERO)
        realised = _ZERO
        last_close: dict[int, Decimal] = {}

        points: list[PortfolioValuePoint] = []
        current = first_day
        while current <= last_day:
            for trade in trades_by_day.get(current, []):
                realised += self._apply(trade, quantities, cost_bases)

            invested = sum(cost_bases.values(), _ZERO)
            market_value = _ZERO
            for company_id, quantity in quantities.items():
                if quantity <= _ZERO:
                    continue
                close = closes_by_company.get(company_id, {}).get(current)
                if close is not None:
                    last_close[company_id] = close
                # Forward-fill: no bar today means no revaluation today. Falling
                # back to cost basis for a company with no bar *ever* keeps a real
                # holding from reading as worthless.
                price = last_close.get(company_id)
                if price is None:
                    market_value += cost_bases.get(company_id, _ZERO)
                else:
                    market_value += quantity * price

            points.append(self._point(current, invested, market_value))
            current += timedelta(days=1)

        if len(points) > MAX_POINTS:
            logger.info(
                "Portfolio history truncated to the most recent %d of %d days.",
                MAX_POINTS,
                len(points),
            )
            points = points[-MAX_POINTS:]

        latest = points[-1]
        return PortfolioHistoryRead(
            points=points,
            total_invested=latest.invested,
            total_market_value=latest.market_value,
            total_profit=latest.profit,
            total_profit_pct=latest.profit_pct,
            realised_profit=_money(realised),
            first_trade_on=first_day,
            as_of=utcnow(),
        )

    @staticmethod
    def _point(on_date: date, invested: Decimal, market_value: Decimal) -> PortfolioValuePoint:
        profit = market_value - invested
        # Percent is undefined with nothing invested - a fully closed portfolio is
        # the normal case, not an error. Reporting 0% would imply "broke even".
        profit_pct = (
            (profit / invested * 100).quantize(_PERCENT, rounding=ROUND_HALF_UP)
            if invested > _ZERO
            else None
        )
        return PortfolioValuePoint(
            on_date=on_date,
            invested=_money(invested),
            market_value=_money(market_value),
            profit=_money(profit),
            profit_pct=profit_pct,
        )

    @staticmethod
    def _apply(
        trade: Trade,
        quantities: dict[int, Decimal],
        cost_bases: dict[int, Decimal],
    ) -> Decimal:
        """Apply one trade in place; return the realised profit it produced.

        Mirrors ``PortfolioService.replay`` deliberately, including clamping an
        oversell rather than raising: a bad ledger row must not blank the chart.
        """
        company_id = trade.company_id
        quantity = trade.quantity
        price = trade.price
        fees = trade.fees

        if trade.side is TradeSide.BUY:
            quantities[company_id] += quantity
            cost_bases[company_id] += quantity * price + fees
            return _ZERO

        held = quantities[company_id]
        sold = min(quantity, held)
        if sold <= _ZERO:
            return -fees

        average_cost = cost_bases[company_id] / held if held > _ZERO else _ZERO
        cost_of_sold = average_cost * sold
        quantities[company_id] = held - sold
        cost_bases[company_id] -= cost_of_sold
        if quantities[company_id] <= _ZERO:
            # Clear the residue so a rounding tail cannot show as a phantom
            # holding worth a fraction of a rupee.
            quantities[company_id] = _ZERO
            cost_bases[company_id] = _ZERO
        return sold * price - fees - cost_of_sold

    def _closes(self, company_ids: list[int]) -> dict[int, dict[date, Decimal]]:
        """``{company_id: {trade_date: close}}`` for every company ever traded."""
        closes: dict[int, dict[date, Decimal]] = {}
        for company_id in company_ids:
            bars = self.companies.list_price_bars(company_id)
            closes[company_id] = {bar.trade_date: bar.close for bar in bars}
        return closes
