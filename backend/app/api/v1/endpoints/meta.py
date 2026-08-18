"""Health and metadata endpoints.

``/meta`` exists so the frontend has exactly one source for the server's
vocabulary - sector labels, horizon options, checklist wording - instead of a
second hard-coded copy that drifts. It is also where the client learns whether the
market data behind every other response is real or generated.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.api.deps import ProviderDep, SessionDep, SettingsDep
from app.core.enums import (
    SECTOR_LABELS,
    MetricVerdict,
    RiskTolerance,
    Sector,
    TimeHorizon,
)
from app.core.logging import get_logger
from app.schemas.meta import EnumOption, HealthRead, MetadataRead, ProviderInfo
from app.schemas.plans import CHECKLIST_QUESTIONS

logger = get_logger(__name__)

router = APIRouter(tags=["meta"])

#: Descriptions shown next to each option in the profile form. Kept here rather
#: than in the enum so the enum stays a vocabulary and this stays copy.
_HORIZON_LABELS: dict[TimeHorizon, tuple[str, str]] = {
    TimeHorizon.SHORT_TERM: (
        "Short term (under a year)",
        "Closer to trading than investing - a different skill, with different risks.",
    ),
    TimeHorizon.MEDIUM_TERM: ("Medium term (1-3 years)", "Long enough to ride out normal swings."),
    TimeHorizon.LONG_TERM: (
        "Long term (3-5+ years)",
        "The horizon the fundamentals checklist is designed for.",
    ),
}

_RISK_LABELS: dict[RiskTolerance, tuple[str, str]] = {
    RiskTolerance.CONSERVATIVE: (
        "Conservative",
        "A large paper loss would be hard to sit through.",
    ),
    RiskTolerance.MODERATE: ("Moderate", "Comfortable with normal volatility on money set aside."),
    RiskTolerance.AGGRESSIVE: (
        "Aggressive",
        "Willing to accept large swings for the chance of higher returns.",
    ),
}

_VERDICT_LABELS: dict[MetricVerdict, tuple[str, str]] = {
    MetricVerdict.STRONG: ("Strong", "Comfortably meets the criteria for this metric."),
    MetricVerdict.ADEQUATE: ("Adequate", "Acceptable, without being a standout."),
    MetricVerdict.WEAK: ("Weak", "Falls short of the criteria - worth understanding why."),
    MetricVerdict.INSUFFICIENT_DATA: (
        "Not enough data",
        "The figures cannot support a judgement. Not the same as a bad result.",
    ),
}


@router.get("/health", response_model=HealthRead, summary="Liveness and dependency check")
def health(session: SessionDep, settings: SettingsDep) -> HealthRead:
    """Report whether the service and its database are usable.

    Runs a real ``SELECT 1``: a health check that only proves the process is
    running will report healthy while every request fails on a dead connection
    pool.
    """
    database_reachable = True
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        # Any failure at all means the database is not reachable from here.
        logger.exception("Health check could not reach the database.")
        database_reachable = False

    return HealthRead(
        status="ok" if database_reachable else "degraded",
        version=__version__,
        environment=settings.environment.value,
        database_reachable=database_reachable,
    )


@router.get("/meta", response_model=MetadataRead, summary="Server vocabulary and data provenance")
def metadata(provider: ProviderDep) -> MetadataRead:
    """Enumerations, labels and the active market data provider.

    Clients should render forms from this response rather than hard-coding option
    lists, and **must** honour ``provider.is_synthetic`` by labelling generated
    figures as such.
    """
    return MetadataRead(
        provider=ProviderInfo(
            name=provider.metadata.name,
            description=provider.metadata.description,
            is_synthetic=provider.metadata.is_synthetic,
            verification_sources=provider.metadata.verification_sources,
            price_delay_minutes=provider.metadata.price_delay_minutes,
        ),
        sectors=[EnumOption(value=sector.value, label=SECTOR_LABELS[sector]) for sector in Sector],
        time_horizons=[
            EnumOption(value=horizon.value, label=label, description=description)
            for horizon, (label, description) in _HORIZON_LABELS.items()
        ],
        risk_tolerances=[
            EnumOption(value=tolerance.value, label=label, description=description)
            for tolerance, (label, description) in _RISK_LABELS.items()
        ],
        metric_verdicts=[
            EnumOption(value=verdict.value, label=label, description=description)
            for verdict, (label, description) in _VERDICT_LABELS.items()
        ],
        prebuy_checklist=[
            EnumOption(value=key, label=question) for key, question in CHECKLIST_QUESTIONS.items()
        ],
    )
