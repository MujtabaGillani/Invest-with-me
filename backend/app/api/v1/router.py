"""Version 1 API router assembly.

Routers are composed here rather than in :mod:`app.main` so that the set of
endpoints in a version is one readable list, and so that adding ``/api/v2`` later
is a new module rather than a rewrite of the application factory.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import Settings
from app.core.logging import get_logger

from .endpoints import admin, alerts, companies, meta, plans, portfolio, profile, watchlist

logger = get_logger(__name__)


def build_api_router(settings: Settings) -> APIRouter:
    """Assemble the v1 router for the given settings.

    Takes settings rather than reading them globally so a test can build a
    production-shaped router (admin endpoints absent) without touching the
    environment.
    """
    router = APIRouter()

    # Meta first: /health and /meta are the two endpoints a client or a probe
    # calls before anything else.
    router.include_router(meta.router)
    router.include_router(companies.router)
    router.include_router(profile.router)
    router.include_router(watchlist.router)
    router.include_router(plans.router)
    router.include_router(portfolio.router)
    router.include_router(alerts.router)

    if settings.is_production:
        logger.info("Production environment: admin market-data endpoints are not mounted.")
    else:
        router.include_router(admin.router)

    return router
