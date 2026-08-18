"""Metadata and health schemas.

The metadata endpoint exists so the frontend never hard-codes a second copy of
the server's vocabulary (sectors, horizons, checklist wording) and so it can
discover, at runtime, whether the market data behind everything it renders is
real or generated.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import STANDARD_DISCLAIMER, Disclaimer, ReadSchema


class HealthRead(ReadSchema):
    """Liveness and dependency check."""

    status: str = Field(description="'ok' or 'degraded'.")
    version: str
    environment: str
    database_reachable: bool


class EnumOption(ReadSchema):
    """A single allowed value with its display label."""

    value: str
    label: str
    description: str | None = None


class ProviderInfo(ReadSchema):
    """Which market data provider is active, and whether to trust its numbers."""

    name: str
    description: str
    is_synthetic: bool = Field(
        description=(
            "True when figures are generated for demonstration. The UI must label the data "
            "accordingly and must not present it as real market data."
        )
    )
    verification_sources: list[str] = Field(
        default_factory=list,
        description="Where to check real figures yourself (guide section 8).",
    )


class MetadataRead(ReadSchema):
    """Everything the client needs to render forms and labels consistently."""

    provider: ProviderInfo
    sectors: list[EnumOption]
    time_horizons: list[EnumOption]
    risk_tolerances: list[EnumOption]
    metric_verdicts: list[EnumOption]
    #: The five pre-buy questions, in guide order, with their field keys.
    prebuy_checklist: list[EnumOption]
    disclaimer: Disclaimer = STANDARD_DISCLAIMER
