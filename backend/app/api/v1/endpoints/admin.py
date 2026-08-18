"""Operational endpoints for refreshing market data.

**Not mounted in production.** :func:`app.api.v1.router.build_api_router` omits
this router when the environment is production, because a refresh rewrites price
and financial history and there is no authentication in v1 to put in front of it.
In a deployed setting the same work belongs in a scheduled job or a CLI command
that runs with real credentials.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ProviderDep, SessionDep
from app.core.logging import get_logger
from app.schemas.common import ReadSchema
from app.services.market_data import DEFAULT_SESSIONS, MarketDataSyncService

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class SyncResultRead(ReadSchema):
    """What a market data refresh changed."""

    companies_created: int
    companies_updated: int
    financial_years_written: int
    price_bars_written: int
    symbols_skipped: list[str]
    provider: str
    provider_is_synthetic: bool


@router.post(
    "/market-data/sync",
    response_model=SyncResultRead,
    summary="Refresh market data from the active provider",
)
def sync_market_data(
    session: SessionDep,
    provider: ProviderDep,
    symbol: Annotated[
        str | None, Query(description="Refresh a single symbol instead of everything.")
    ] = None,
    sessions: Annotated[
        int, Query(ge=30, le=2000, description="Price sessions to load per company.")
    ] = DEFAULT_SESSIONS,
) -> SyncResultRead:
    """Reload companies, financial statements and price history.

    Existing financials and prices for each company are **replaced**, not merged -
    restatements and split-adjusted prices legitimately change history, and a merge
    would leave a mix of old and new figures. The commit happens here so a failure
    mid-refresh rolls the whole thing back rather than leaving half the market
    updated.
    """
    service = MarketDataSyncService(session, provider)
    report = (
        service.sync_symbol(symbol, sessions=sessions)
        if symbol
        else service.sync_all(sessions=sessions, skip_existing=False)
    )
    session.commit()

    return SyncResultRead(
        companies_created=report.companies_created,
        companies_updated=report.companies_updated,
        financial_years_written=report.financial_years_written,
        price_bars_written=report.price_bars_written,
        symbols_skipped=report.symbols_skipped,
        provider=provider.metadata.name,
        provider_is_synthetic=provider.metadata.is_synthetic,
    )
