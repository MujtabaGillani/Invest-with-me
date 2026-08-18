"""Seeded (synthetic) market data provider.

Expands the compact company profiles in ``app/data/seed_companies.json`` into
five years of financial statements and roughly fifteen months of daily price
bars.

**The figures it produces are invented.** Symbols, names and sectors are real PSX
listings; every number is generated. :attr:`metadata.is_synthetic` is ``True`` and
the API propagates that flag so the UI can label the data - see
``docs/ARCHITECTURE.md`` for why that flag is treated as load-bearing rather than
cosmetic.

Why generate rather than ship a snapshot of real figures:

* No licensing or terms-of-service question about redistributing market data.
* The dataset deliberately contains companies that fail specific checks - an
  eroding margin, a falling knife, a loss-maker with no meaningful P/E, a
  profitable company with negative cash flow - so every branch of the analysis
  engines is exercised by the demo data itself.
* It is **deterministic**: the same symbol and as-of date always produce the same
  series, so screenshots, tests and bug reports are reproducible.

Determinism detail: the pseudo-random walk is seeded with ``crc32`` of the symbol
rather than ``hash()``, because Python's string hash is randomised per process
and would give a different chart on every restart.
"""

from __future__ import annotations

import json
import random
import zlib
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from importlib import resources
from typing import Any

from app.core.enums import Sector
from app.core.errors import ProviderError
from app.core.logging import get_logger
from app.providers.base import (
    CompanyRecord,
    FinancialsRecord,
    PriceBarRecord,
    ProviderMetadata,
)

logger = get_logger(__name__)

#: Package-relative location of the profile file.
_DATA_PACKAGE = "app.data"
_DATA_FILE = "seed_companies.json"

#: Fiscal years generated for every company.
_YEARS_OF_HISTORY = 5
#: Trading sessions generated - about fifteen months, comfortably more than the
#: 200 sessions the long moving average needs.
_DEFAULT_SESSIONS = 320

_TWO_PLACES = Decimal("0.01")
_FOUR_PLACES = Decimal("0.0001")


def _money(value: float) -> Decimal:
    """Round a generated float to a 2dp Decimal for persistence."""
    return Decimal(repr(round(value, 2))).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _per_share(value: float) -> Decimal:
    """Round a per-share figure to 4dp - EPS and dividends need the precision."""
    return Decimal(repr(round(value, 4))).quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)


@lru_cache(maxsize=1)
def _load_profiles() -> dict[str, dict[str, Any]]:
    """Read and index the profile file by symbol.

    Cached: the file is static, and re-parsing it per request would be pure
    waste. :func:`reset_cache` clears it for tests that patch the data.
    """
    try:
        raw = resources.files(_DATA_PACKAGE).joinpath(_DATA_FILE).read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderError(
            "The seeded market data file could not be read.",
            details={"file": f"{_DATA_PACKAGE}/{_DATA_FILE}"},
        ) from exc

    companies = payload.get("companies")
    if not isinstance(companies, list) or not companies:
        raise ProviderError("The seeded market data file contains no companies.")

    indexed: dict[str, dict[str, Any]] = {}
    for entry in companies:
        symbol = str(entry["symbol"]).upper()
        if symbol in indexed:
            raise ProviderError(
                "Duplicate symbol in the seeded market data file.", details={"symbol": symbol}
            )
        indexed[symbol] = entry
    return indexed


def reset_cache() -> None:
    """Drop the parsed-file cache. Used by tests."""
    _load_profiles.cache_clear()


class SeededMarketDataProvider:
    """Deterministic, synthetic implementation of
    :class:`~app.providers.base.MarketDataProvider`.

    :param as_of: the date the generated price series ends on. Defaults to today
        so the demo always looks current; tests pin it for reproducibility.
    :param latest_fiscal_year: the most recent fiscal year to generate. Defaults
        to the year before ``as_of``, matching the real world - a company's full
        prior-year accounts are what is available at any given moment.
    """

    def __init__(self, *, as_of: date | None = None, latest_fiscal_year: int | None = None) -> None:
        self._as_of = as_of or date.today()
        self._latest_fiscal_year = latest_fiscal_year or (self._as_of.year - 1)

    # -- Protocol ---------------------------------------------------------

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name="seeded",
            description=(
                "Illustrative, generated dataset for real PSX ticker symbols. Financial "
                "figures and prices are synthetic and must not be used for real investment "
                "decisions."
            ),
            is_synthetic=True,
            # Left as "unknown" rather than 0: these prices are not delayed, but
            # they are not a market either, and reporting "real time" for invented
            # figures would be the more misleading of the two.
            price_delay_minutes=None,
            verification_sources=[
                "PSX filings and announcements (PUCARS) - https://dps.psx.com.pk/",
                "Sarmaaya - https://sarmaaya.pk/",
                "SCSTrade - https://www.scstrade.com/",
                "Company annual and quarterly reports",
            ],
        )

    def list_companies(self) -> Sequence[CompanyRecord]:
        records: list[CompanyRecord] = []
        for symbol, entry in sorted(_load_profiles().items()):
            try:
                sector = Sector(entry["sector"])
            except ValueError as exc:
                # A typo in the data file should name itself, not surface as a
                # confusing enum error deep inside the seeding routine.
                raise ProviderError(
                    "Unknown sector in the seeded market data file.",
                    details={"symbol": symbol, "sector": entry.get("sector")},
                ) from exc
            records.append(
                CompanyRecord(
                    symbol=symbol,
                    name=entry["name"],
                    sector=sector,
                    business_summary=entry.get("business_summary"),
                    website=entry.get("website"),
                )
            )
        return records

    def fetch_financials(self, symbol: str) -> Sequence[FinancialsRecord]:
        entry = _load_profiles().get(symbol.upper())
        if entry is None:
            return []
        return self._generate_financials(entry["profile"])

    def fetch_price_history(
        self, symbol: str, sessions: int = _DEFAULT_SESSIONS
    ) -> Sequence[PriceBarRecord]:
        symbol = symbol.upper()
        entry = _load_profiles().get(symbol)
        if entry is None:
            return []
        return self._generate_price_history(symbol, entry["profile"], sessions)

    # -- Generation -------------------------------------------------------

    def _generate_financials(self, profile: dict[str, Any]) -> list[FinancialsRecord]:
        """Back-cast five years of statements from the latest-year profile.

        Each year is derived from the latest figures rather than compounded
        forward from the oldest, so editing ``latest_revenue`` in the data file
        changes the headline number without silently rescaling history.
        """
        latest_revenue = float(profile["latest_revenue"])
        cagr = float(profile["revenue_cagr_pct"]) / 100.0
        wobble = float(profile.get("revenue_wobble_pct", 0.0)) / 100.0
        latest_margin = float(profile["net_margin_pct"])
        margin_drift = float(profile["margin_drift_pp"])
        shares = float(profile["shares_outstanding"])
        equity_to_revenue = float(profile["equity_to_revenue"])
        latest_gearing = float(profile["debt_to_equity"])
        gearing_drift = float(profile.get("debt_drift_pct", 0.0)) / 100.0
        ocf_multiple = float(profile["ocf_to_profit"])
        capex_share = float(profile["capex_to_revenue"])
        payout = float(profile["payout_ratio"])

        records: list[FinancialsRecord] = []
        for offset in range(_YEARS_OF_HISTORY - 1, -1, -1):
            # offset 0 == latest year, offset 4 == oldest.
            fiscal_year = self._latest_fiscal_year - offset

            # Revenue: discount back at the CAGR, then alternate a wobble by year
            # so growth is not implausibly smooth. Odd offsets are nudged down,
            # which is what makes the "inconsistent grower" profiles read as one.
            revenue = latest_revenue / ((1.0 + cagr) ** offset)
            if wobble and offset:
                revenue *= 1.0 + (wobble if offset % 2 == 0 else -wobble)

            margin_pct = latest_margin - margin_drift * offset
            net_profit = revenue * margin_pct / 100.0
            eps = net_profit / shares if shares else None

            equity = revenue * equity_to_revenue
            gearing = latest_gearing / ((1.0 + gearing_drift) ** offset)
            debt = equity * max(gearing, 0.0)
            # Assets are approximated as funded capital plus non-debt liabilities;
            # nothing in the analysis depends on this figure, it is carried so the
            # balance sheet looks complete on screen.
            total_assets = equity + debt + revenue * 0.25

            operating_cash_flow = net_profit * ocf_multiple
            capital_expenditure = revenue * capex_share
            dividend_per_share = (eps or 0.0) * payout if payout > 0 and (eps or 0) > 0 else 0.0

            records.append(
                FinancialsRecord(
                    fiscal_year=fiscal_year,
                    revenue=_money(revenue),
                    net_profit=_money(net_profit),
                    eps=_per_share(eps) if eps is not None else None,
                    total_assets=_money(total_assets),
                    total_equity=_money(equity),
                    total_debt=_money(debt),
                    operating_cash_flow=_money(operating_cash_flow),
                    capital_expenditure=_money(capital_expenditure),
                    dividend_per_share=_per_share(dividend_per_share),
                    shares_outstanding=_money(shares),
                    source=f"Generated demonstration data (FY{fiscal_year})",
                )
            )
        return records

    def _generate_price_history(
        self, symbol: str, profile: dict[str, Any], sessions: int
    ) -> list[PriceBarRecord]:
        """Build a deterministic daily series ending at ``base_price``.

        A pseudo-random walk supplies the texture, then both endpoints are pinned:
        the last close is exactly ``base_price`` and the first is exactly the
        price implied by ``price_trend_pct``. Pinning only the end point is not
        enough - over 320 sessions the accumulated shocks wander far enough that a
        company configured to be down 30% can come out up 20%, which would make
        the deliberately-troubled demo companies unusable for demonstrating the
        falling-knife red flag.

        The correction is a geometric interpolation between the two endpoint
        ratios, so it stretches the path without flattening the day-to-day
        movement the indicators read.
        """
        sessions = max(int(sessions), 2)
        base_price = float(profile["base_price"])
        trend_pct = float(profile.get("price_trend_pct", 0.0))
        volatility = float(profile.get("volatility_pct", 2.0)) / 100.0

        rng = random.Random(zlib.crc32(symbol.encode("utf-8")))

        start_price = base_price / (1.0 + trend_pct / 100.0)
        # Per-session drift that would take start_price to base_price on its own.
        drift = (base_price / start_price) ** (1.0 / (sessions - 1)) - 1.0

        trading_days = self._trading_days(sessions)
        closes: list[float] = []
        price = start_price
        for index in range(sessions):
            if index:
                shock = rng.gauss(0.0, volatility)
                # Clamp to +/-3 sigma: PSX has circuit breakers, and an untamed
                # gaussian tail would produce a 20% single-session gap that makes
                # the demo chart look broken.
                shock = max(min(shock, volatility * 3), -volatility * 3)
                price *= 1.0 + drift + shock
            closes.append(max(price, 0.5))

        # Pin both endpoints. `start_correction` and `end_correction` are each
        # applied with a weight that slides from 1 to 0 across the series.
        last_index = sessions - 1
        start_correction = start_price / closes[0]
        end_correction = base_price / closes[-1]
        closes = [
            close
            * (start_correction ** ((last_index - index) / last_index))
            * (end_correction ** (index / last_index))
            for index, close in enumerate(closes)
        ]

        bars: list[PriceBarRecord] = []
        average_volume = self._baseline_volume(base_price)
        for index, (trade_date, close) in enumerate(zip(trading_days, closes, strict=True)):
            previous_close = closes[index - 1] if index else close
            open_price = previous_close * (1.0 + rng.uniform(-0.004, 0.004))
            high = max(open_price, close) * (1.0 + rng.uniform(0.0, 0.012))
            low = min(open_price, close) * (1.0 - rng.uniform(0.0, 0.012))
            # Volume rises with the size of the move, which is what makes the
            # volume-confirmation indicator meaningful on generated data.
            move = abs(close - previous_close) / previous_close if previous_close else 0.0
            volume = int(average_volume * (0.55 + rng.random() * 0.9 + move * 22))

            bars.append(
                PriceBarRecord(
                    trade_date=trade_date,
                    open=_money(open_price),
                    high=_money(high),
                    low=_money(low),
                    close=_money(close),
                    volume=max(volume, 100),
                )
            )
        return bars

    def _trading_days(self, sessions: int) -> list[date]:
        """The last ``sessions`` weekdays ending on or before ``as_of``.

        Weekends are skipped; public holidays are not modelled. The technical
        engine only requires strictly ascending dates, so an unmodelled holiday
        changes nothing about the analysis.
        """
        days: list[date] = []
        cursor = self._as_of
        while len(days) < sessions:
            if cursor.weekday() < 5:  # Monday-Friday
                days.append(cursor)
            cursor -= timedelta(days=1)
        return sorted(days)

    @staticmethod
    def _baseline_volume(price: float) -> int:
        """Rough inverse relationship between share price and traded volume.

        A PKR 20 share trades in millions; a PKR 7,000 share trades in hundreds.
        Modelling that keeps the volume column plausible rather than uniform.
        """
        if price >= 2000:
            return 3_000
        if price >= 500:
            return 60_000
        if price >= 100:
            return 900_000
        return 4_500_000
