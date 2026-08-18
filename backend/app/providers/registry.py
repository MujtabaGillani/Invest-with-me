"""Provider lookup.

One dictionary, one factory. Adding a real PSX feed means writing the class and
adding a line here; nothing else in the application changes.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings, get_settings
from app.core.errors import ProviderError
from app.core.logging import get_logger
from app.providers.base import MarketDataProvider
from app.providers.seeded import SeededMarketDataProvider

logger = get_logger(__name__)


def _build_psx_provider() -> MarketDataProvider:
    """Construct the real PSX provider, importing it only when selected.

    Deliberately a function rather than a module-level import: ``app.providers.psx``
    pulls in ``psxdata``, and therefore pandas, pyarrow and numpy. That is tens of
    megabytes and a visible import delay, which every test run and every default
    checkout - all of which use the seeded provider - would otherwise pay for
    nothing.
    """
    from app.providers.psx import PsxDataProvider

    return PsxDataProvider()


#: Registered factories keyed by the value of ``PSX_MARKET_DATA_PROVIDER``.
_FACTORIES: dict[str, Callable[[], MarketDataProvider]] = {
    "seeded": SeededMarketDataProvider,
    "psx": _build_psx_provider,
}


def available_providers() -> list[str]:
    """Names accepted by :func:`build_provider`."""
    return sorted(_FACTORIES)


def build_provider(settings: Settings | None = None) -> MarketDataProvider:
    """Instantiate the provider named in configuration.

    :raises ProviderError: when the configured name is not registered. Failing
        loudly at startup is the point - a silent fallback to synthetic data
        would be the most dangerous possible default in this application.
    """
    settings = settings or get_settings()
    factory = _FACTORIES.get(settings.market_data_provider)
    if factory is None:
        raise ProviderError(
            f"Unknown market data provider '{settings.market_data_provider}'.",
            details={"available": available_providers()},
        )
    provider = factory()
    if provider.metadata.is_synthetic:
        logger.warning(
            "Market data provider '%s' returns SYNTHETIC data - not for real decisions.",
            provider.metadata.name,
        )
    return provider
