"""FastAPI dependencies.

Endpoints declare what they need (a session, the current user, a service) and get
it from here. Two consequences worth stating, because they are the reason this
module exists rather than endpoints constructing their own collaborators:

* **Tests override one function, not many.** ``app.dependency_overrides`` can
  swap the session or the current user for the whole application.
* **The authentication seam is a single function.** :func:`get_current_user` is
  the only place that decides whose data a request sees. Adding real login means
  changing it and nothing else.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import Sector, TradePlanStatus
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.user import User
from app.providers.base import MarketDataProvider
from app.providers.registry import build_provider
from app.repositories.users import UserRepository
from app.schemas.common import PaginationParams
from app.services.alerts import AlertService
from app.services.analysis import AnalysisService
from app.services.companies import CompanyService
from app.services.plans import TradePlanService
from app.services.portfolio import PortfolioService
from app.services.profile import ProfileService
from app.services.watchlist import WatchlistService

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]


def get_market_data_provider(request: Request) -> MarketDataProvider:
    """The provider bound at application startup.

    Read from ``app.state`` rather than constructed per request: a real provider
    will hold an HTTP client and a cache, and rebuilding it per request would
    discard both. Falls back to building one so that a directly-constructed
    ``TestClient`` without a lifespan still works.
    """
    provider: MarketDataProvider | None = getattr(request.app.state, "market_data_provider", None)
    if provider is None:  # pragma: no cover - only without the lifespan
        provider = build_provider()
        request.app.state.market_data_provider = provider
    return provider


ProviderDep = Annotated[MarketDataProvider, Depends(get_market_data_provider)]


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def get_current_user(session: SessionDep, settings: SettingsDep) -> User:
    """Resolve the account this request acts on.

    **This is the authentication seam.** v1 is single-user: the account named by
    ``PSX_DEFAULT_USER_EMAIL`` is resolved (and created on first use) for every
    request. There is no login, no token and no authorisation check.

    That is a deliberate, documented v1 scope decision - not an oversight - and it
    is safe only because the service is intended to run locally for one person.
    Every user-owned table already carries ``user_id`` and every repository read
    is scoped by it, so introducing real authentication is a change to this
    function alone.
    """
    users = UserRepository(session)
    user = users.get_or_create(settings.default_user_email, settings.default_user_name)
    # get_or_create may have inserted a row; commit so downstream writes in this
    # request can reference it and so a read-only request still persists the user.
    if session.new:
        session.commit()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Query parameter bundles
# ---------------------------------------------------------------------------


def pagination_params(
    limit: Annotated[int, Query(ge=1, le=200, description="Rows per page.")] = 50,
    offset: Annotated[int, Query(ge=0, description="Rows to skip.")] = 0,
) -> PaginationParams:
    """Shared ``limit``/``offset`` query parameters."""
    return PaginationParams(limit=limit, offset=offset)


Pagination = Annotated[PaginationParams, Depends(pagination_params)]

SectorFilter = Annotated[Sector | None, Query(description="Restrict results to one PSX sector.")]
PlanStatusFilter = Annotated[
    TradePlanStatus | None, Query(description="Restrict results to one plan status.")
]


# ---------------------------------------------------------------------------
# Services
#
# Thin factories. Each takes the request-scoped session so that every service
# used by one request shares one transaction.
# ---------------------------------------------------------------------------


def get_company_service(session: SessionDep) -> CompanyService:
    return CompanyService(session)


def get_analysis_service(session: SessionDep) -> AnalysisService:
    return AnalysisService(session)


def get_profile_service(session: SessionDep) -> ProfileService:
    return ProfileService(session)


def get_watchlist_service(session: SessionDep) -> WatchlistService:
    return WatchlistService(session)


def get_plan_service(session: SessionDep) -> TradePlanService:
    return TradePlanService(session)


def get_portfolio_service(session: SessionDep) -> PortfolioService:
    return PortfolioService(session)


def get_alert_service(session: SessionDep) -> AlertService:
    return AlertService(session)


CompanyServiceDep = Annotated[CompanyService, Depends(get_company_service)]
AnalysisServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]
ProfileServiceDep = Annotated[ProfileService, Depends(get_profile_service)]
WatchlistServiceDep = Annotated[WatchlistService, Depends(get_watchlist_service)]
PlanServiceDep = Annotated[TradePlanService, Depends(get_plan_service)]
PortfolioServiceDep = Annotated[PortfolioService, Depends(get_portfolio_service)]
AlertServiceDep = Annotated[AlertService, Depends(get_alert_service)]
