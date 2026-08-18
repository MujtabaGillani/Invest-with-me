"""Portfolio and trade ledger endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, PortfolioServiceDep, ProviderDep, SessionDep
from app.schemas.portfolio import PortfolioRead, TradeCreate, TradeRead
from app.schemas.screener import PortfolioHistoryRead
from app.services.portfolio_history import PortfolioHistoryService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get(
    "/history",
    response_model=PortfolioHistoryRead,
    summary="Invested versus value over time",
    response_description="Daily invested, market value and profit, oldest first.",
)
def portfolio_history(session: SessionDep, user: CurrentUser) -> PortfolioHistoryRead:
    """The profit/loss series behind the chart.

    Reconstructed from the trade ledger and stored closes on every request rather
    than stored, so it can never disagree with the trades that produced it. Days
    when nothing traded carry the previous close forward - see the service module
    docstring for why that is the honest choice rather than dropping or
    interpolating them.
    """
    return PortfolioHistoryService(session).history(user.id)


@router.get(
    "",
    response_model=PortfolioRead,
    summary="Get the portfolio",
    response_description="Holdings, sector allocation and concentration warnings.",
)
def get_portfolio(
    service: PortfolioServiceDep, user: CurrentUser, provider: ProviderDep
) -> PortfolioRead:
    """Current holdings, valued at the latest stored close.

    Holdings are rebuilt from the trade ledger on every request rather than read
    from a holdings table, so they can never disagree with the trades that produced
    them. ``market_data_is_synthetic`` tells the client whether the prices behind
    these valuations are real - the UI must label them when they are not.
    """
    return service.get_portfolio(user.id, market_data_is_synthetic=provider.metadata.is_synthetic)


@router.get(
    "/trades",
    response_model=list[TradeRead],
    summary="List recorded trades",
)
def list_trades(
    service: PortfolioServiceDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[TradeRead]:
    """The trade ledger, newest first."""
    return service.list_trades(user.id, limit=limit)


@router.post(
    "/trades",
    response_model=TradeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a trade",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Unknown symbol."},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Selling more shares than are held, or an invalid plan reference."
        },
    },
)
def record_trade(
    payload: TradeCreate, service: PortfolioServiceDep, user: CurrentUser
) -> TradeRead:
    """Append a buy or sell to the ledger.

    A buy against a plan that is READY marks that plan EXECUTED: the commitment has
    been acted on, and its profit target and stop-loss now govern real money. If no
    ``plan_id`` is supplied, a READY plan for the same company is linked
    automatically.
    """
    return service.record_trade(user.id, payload)
