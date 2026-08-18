"""Business logic layer.

Each service takes a :class:`~sqlalchemy.orm.Session` and owns the rules for one
part of the domain. Services may call other services (plans need a portfolio
value; alerts need both), and they own their transaction boundaries: a method
that changes state commits, a read method does not.

Import direction, enforced by review rather than tooling:

    api -> services -> repositories -> models
                    -> analysis (pure)
                    -> providers
"""

from app.services.alerts import AlertService
from app.services.analysis import AnalysisService
from app.services.companies import CompanyService
from app.services.market_data import MarketDataSyncService
from app.services.plans import TradePlanService
from app.services.portfolio import PortfolioService
from app.services.profile import ProfileService
from app.services.watchlist import WatchlistService

__all__ = [
    "AlertService",
    "AnalysisService",
    "CompanyService",
    "MarketDataSyncService",
    "PortfolioService",
    "ProfileService",
    "TradePlanService",
    "WatchlistService",
]
