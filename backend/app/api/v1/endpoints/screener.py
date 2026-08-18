"""The simplified buy/sell endpoints.

Two endpoints backing a screen for someone who wants "what could I buy" and "what
should I sell" rather than a per-company checklist. Both responses carry the active
provider's honesty flags - ``data_is_synthetic`` and ``price_delay_minutes`` - so
the client can never present a ranked list of generated figures, or a
fifteen-minute-old price, as the live market.

Neither endpoint returns a prediction. See the module docstring of
:mod:`app.services.screener` for the line being held and why it holds.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import (
    AnalysisServiceDep,
    CurrentUser,
    PortfolioServiceDep,
    ProviderDep,
    SessionDep,
)
from app.schemas.screener import BuyCandidatesRead, SellReviewRead
from app.services.screener import ScreenerService

router = APIRouter(prefix="/screener", tags=["screener"])


def _service(
    session: SessionDep,
    analysis: AnalysisServiceDep,
    portfolio: PortfolioServiceDep,
    provider: ProviderDep,
) -> ScreenerService:
    """Assemble the screener with the active provider's provenance attached.

    Built here rather than in ``deps.py`` because it is the only service needing
    both analysis and portfolio plus provider metadata, and threading that through
    a shared dependency would make every other service carry it.
    """
    return ScreenerService(
        session,
        analysis,
        portfolio,
        price_delay_minutes=provider.metadata.price_delay_minutes,
        data_is_synthetic=provider.metadata.is_synthetic,
    )


@router.get(
    "/buy-candidates",
    response_model=BuyCandidatesRead,
    summary="Companies ranked by how many checklist criteria they meet",
    response_description=(
        "Ranked shortlist with the reasons in plain language, the weak spots, and a "
        "suggested position size and exit levels derived from your own limits."
    ),
)
def buy_candidates(
    session: SessionDep,
    analysis: AnalysisServiceDep,
    portfolio: PortfolioServiceDep,
    provider: ProviderDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=50, description="How many companies to return.")] = 10,
) -> BuyCandidatesRead:
    """Rank the companies with stored data by the criteria they currently meet.

    **This is not a prediction and not advice to buy.** The ordering reflects
    published accounts - how many of the seven checks each company passes right now
    - and nothing about future prices. ``unavailable_checks`` names the criteria that
    could not be run for any company because the active data source does not publish
    the figures, which is a property of the source and not of the companies.
    """
    return _service(session, analysis, portfolio, provider).buy_candidates(user.id, limit=limit)


@router.get(
    "/sell-review",
    response_model=SellReviewRead,
    summary="Holdings that have crossed one of your own rules",
    response_description="Crossed exit rules first, then positions needing a decision.",
)
def sell_review(
    session: SessionDep,
    analysis: AnalysisServiceDep,
    portfolio: PortfolioServiceDep,
    provider: ProviderDep,
    user: CurrentUser,
) -> SellReviewRead:
    """Check every open holding against the exit rules the user committed to.

    The app does not decide whether to sell. It reports that a line the user drew -
    a profit target, a stop-loss, a review interval, a concentration limit - has been
    crossed, and quotes the rule back to them. A holding with no exit rules at all is
    listed too, because that is the decision most worth making before it is urgent.
    """
    return _service(session, analysis, portfolio, provider).sell_review(user.id)
