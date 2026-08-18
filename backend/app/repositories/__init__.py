"""Data access layer. See :mod:`app.repositories.base` for the layer contract."""

from app.repositories.alerts import AlertRepository
from app.repositories.companies import CompanyRepository
from app.repositories.plans import TradePlanRepository
from app.repositories.trades import TradeRepository
from app.repositories.users import InvestorProfileRepository, UserRepository
from app.repositories.watchlist import WatchlistRepository

__all__ = [
    "AlertRepository",
    "CompanyRepository",
    "InvestorProfileRepository",
    "TradePlanRepository",
    "TradeRepository",
    "UserRepository",
    "WatchlistRepository",
]
