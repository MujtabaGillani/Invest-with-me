"""SQLAlchemy ORM models.

Importing this package registers every model on ``Base.metadata``. Alembic's
``env.py`` and the test fixtures both rely on that, so a new model **must** be
added to the imports below or it will be missing from generated migrations.
"""

from app.models.alert import Alert
from app.models.company import Company
from app.models.financials import AnnualFinancials
from app.models.investor_profile import InvestorProfile
from app.models.plan_review import PlanReview
from app.models.price import PriceBar
from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from app.models.user import User
from app.models.watchlist import WatchlistItem

__all__ = [
    "Alert",
    "AnnualFinancials",
    "Company",
    "InvestorProfile",
    "PlanReview",
    "PriceBar",
    "Trade",
    "TradePlan",
    "User",
    "WatchlistItem",
]
