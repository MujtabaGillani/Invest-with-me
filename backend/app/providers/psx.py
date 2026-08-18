"""Real PSX market data provider.

Sources **real** figures, so :attr:`ProviderMetadata.is_synthetic` is ``False``
and the UI stops labelling the data as illustrative. It composes two upstreams,
because no single free source carries everything the analysis engines want:

===================  =======================================================
Companies, prices    ``psxdata`` (MIT), which scrapes the PSX website. Gives
                     the full listed universe with names and sector names, and
                     daily OHLCV *including* high and low.
Annual financials    The PSX Data Portal company page
                     (``dps.psx.com.pk/company/<SYMBOL>``), which publishes a
                     four-year table of Sales, Profit after Taxation and EPS.
===================  =======================================================

Why two sources rather than one: ``psxdata.fundamentals()`` is not what its name
suggests - it returns the *filing list* (titles and links to PDFs), and for many
symbols it returns nothing at all. Verified against LUCK, which yields an empty
frame. The figures themselves only exist as text on the company page or inside
the annual-report PDFs.

**What this provider cannot supply, and why that is visible rather than hidden.**
Neither upstream publishes the balance sheet or the cash flow statement, so
``total_assets``, ``total_equity``, ``total_debt``, ``operating_cash_flow``,
``capital_expenditure`` and ``dividend_per_share`` are left as ``None``. The
analysis engines already treat a missing input as ``INSUFFICIENT_DATA`` with an
explanation rather than as a bad result, so the consequence is that
debt-to-equity, free cash flow and the dividend check report "not enough data"
instead of guessing. That is the intended behaviour: see
``app/analysis/fundamentals.py``, whose contract is that "we don't know" must
never be reported as "it's bad". Those six fields are what a manual-entry path
(or a licensed feed) would fill in later.

Known limitations, all of them properties of the upstream data rather than bugs:

* **Prices are not adjusted** for bonus issues or splits. PSX publishes the
  as-traded series, and bonus issues are common in Pakistan, so a moving average
  spanning a corporate action is comparing two different share bases. The same
  applies to the reported EPS series - see :func:`_annual_financials`.
* **Quotes are delayed, not live.** ``psxdata`` caches the screener for fifteen
  minutes, which reflects the freshness of the public source. Real-time PSX data
  requires a licence from the exchange. :meth:`fetch_quote` therefore returns the
  observation time alongside the price so callers can show its age instead of
  implying a tick.
* **Terms of use.** PSX prohibits redistribution and commercial use of its market
  data without a licence (``marketdatarequest@psx.com.pk``). Reading the public
  site for one's own use is a different matter from republishing it; anything
  public-facing needs that licence.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Final

from app.core.clock import utcnow
from app.core.enums import Sector
from app.core.errors import ProviderError
from app.core.logging import get_logger
from app.providers.base import (
    CompanyRecord,
    FinancialsRecord,
    PriceBarRecord,
    ProviderMetadata,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

logger = get_logger(__name__)

#: Base URL for the company pages that carry the annual figures.
COMPANY_PAGE_URL: Final = "https://dps.psx.com.pk/company/{symbol}"

#: PSX serves a plain browser page; the default ``requests`` agent gets a 403.
_HTTP_HEADERS: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

_HTTP_TIMEOUT_SECONDS: Final = 30.0

#: PSX reports statement figures in **thousands** of rupees ("136,527,017" on
#: Lucky Cement's page is PKR 136.5 billion of sales). EPS is a per-share rupee
#: figure and is *not* scaled.
_THOUSANDS: Final = Decimal(1000)

#: Roughly 250 sessions a year, so this converts a session count into a calendar
#: window with enough slack for weekends and public holidays. Over-fetching is
#: harmless - the caller slices the tail - while under-fetching would silently
#: shorten a 200-day moving average.
_CALENDAR_DAYS_PER_SESSION: Final = 1.6

#: PSX sector names (as published by ``psxdata.sectors()``) mapped onto our own
#: vocabulary. Kept explicit rather than derived by slugifying, because the
#: mapping is not one-to-one: PSX splits oil & gas into exploration and
#: marketing, and our original ``OIL_AND_GAS`` member means exploration.
#: An unrecognised name degrades to ``OTHER`` with a warning rather than raising,
#: since PSX occasionally adds a sector and a whole sync should not fail for it.
_SECTOR_BY_PSX_NAME: Final[dict[str, Sector]] = {
    "AUTOMOBILE ASSEMBLER": Sector.AUTOMOBILE_ASSEMBLER,
    "AUTOMOBILE PARTS & ACCESSORIES": Sector.AUTOMOBILE_PARTS,
    "CABLE & ELECTRICAL GOODS": Sector.CABLE_AND_ELECTRICAL_GOODS,
    "CEMENT": Sector.CEMENT,
    "CHEMICAL": Sector.CHEMICAL,
    "CLOSE - END MUTUAL FUND": Sector.CLOSE_END_MUTUAL_FUND,
    "COMMERCIAL BANKS": Sector.COMMERCIAL_BANKS,
    "ENGINEERING": Sector.ENGINEERING,
    "FERTILIZER": Sector.FERTILIZER,
    "FOOD & PERSONAL CARE PRODUCTS": Sector.FOOD_AND_PERSONAL_CARE,
    "GLASS & CERAMICS": Sector.GLASS_AND_CERAMICS,
    "INSURANCE": Sector.INSURANCE,
    "INV. BANKS / INV. COS. / SECURITIES COS.": Sector.INVESTMENT_BANKS,
    "JUTE": Sector.JUTE,
    "LEASING COMPANIES": Sector.LEASING,
    "LEATHER & TANNERIES": Sector.LEATHER_AND_TANNERIES,
    "MISCELLANEOUS": Sector.MISCELLANEOUS,
    "MODARABAS": Sector.MODARABAS,
    "OIL & GAS EXPLORATION COMPANIES": Sector.OIL_AND_GAS,
    "OIL & GAS MARKETING COMPANIES": Sector.OIL_AND_GAS_MARKETING,
    "PAPER, BOARD & PACKAGING": Sector.PAPER_AND_PACKAGING,
    "PHARMACEUTICALS": Sector.PHARMACEUTICALS,
    "POWER GENERATION & DISTRIBUTION": Sector.POWER_GENERATION,
    "REFINERY": Sector.REFINERY,
    "SUGAR & ALLIED INDUSTRIES": Sector.SUGAR,
    "SYNTHETIC & RAYON": Sector.SYNTHETIC_AND_RAYON,
    "TECHNOLOGY & COMMUNICATION": Sector.TECHNOLOGY_AND_COMMUNICATION,
    "TEXTILE COMPOSITE": Sector.TEXTILE_COMPOSITE,
    "TEXTILE SPINNING": Sector.TEXTILE_SPINNING,
    "TEXTILE WEAVING": Sector.TEXTILE_WEAVING,
    "TOBACCO": Sector.TOBACCO,
    "TRANSPORT": Sector.TRANSPORT,
    "VANASPATI & ALLIED INDUSTRIES": Sector.VANASPATI,
    "WOOLLEN": Sector.WOOLLEN,
    "REAL ESTATE INVESTMENT TRUST": Sector.REIT,
    "EXCHANGE TRADED FUNDS": Sector.EXCHANGE_TRADED_FUNDS,
    "PROPERTY": Sector.PROPERTY,
    "APPAREL": Sector.APPAREL,
}

#: Row labels on the company page's annual table, mapped to our field names.
#: PSX's wording has varied ("Sales" vs "Revenue"), so each field accepts
#: several labels; matching is case-insensitive on the stripped text.
_ANNUAL_ROW_LABELS: Final[dict[str, tuple[str, ...]]] = {
    "revenue": ("sales", "revenue", "net sales", "total revenue"),
    "net_profit": ("profit after taxation", "profit after tax", "net profit"),
    "eps": ("eps", "earnings per share"),
}


@dataclass(frozen=True, slots=True)
class Quote:
    """A delayed price observation, stamped with when it was read.

    ``observed_at`` is deliberately part of the value rather than something the
    caller infers: the whole point is that this figure has an age, and a UI that
    cannot state the age should not present the number as current.
    """

    symbol: str
    price: Decimal
    observed_at: datetime
    change_pct: float | None = None
    pe_ratio: float | None = None
    dividend_yield: float | None = None
    volume_avg_30d: int | None = None
    #: Upstream cache window, in minutes - the floor on how stale ``price`` is.
    delay_minutes: int = 15


def _to_decimal(raw: Any, *, scale: Decimal = Decimal(1)) -> Decimal | None:
    """Parse one PSX-formatted number, or ``None`` when it is not a number.

    Handles the three conventions the pages use: thousands separators
    (``"136,527,017"``), accounting negatives (``"(56.08)"``), and a range of
    placeholders for "not reported" (``"-"``, ``"N/A"``, an empty cell). Returns
    ``None`` for anything unparseable, because a missing figure must reach the
    analysis layer as absent rather than as zero - ``0`` would be scored as a
    genuinely terrible result.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text in {"-", "--", "N/A", "n/a", "NA", "nan", "NaN", "None"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = text.replace(",", "").replace("Rs.", "").replace("%", "").strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ArithmeticError):
        return None
    if negative:
        value = -value
    return value * scale


def _sector_for(psx_sector_name: Any) -> Sector:
    """Map a PSX sector name onto our vocabulary, degrading to ``OTHER``.

    Two different situations both land on ``OTHER``, and only one of them is
    worth an operator's attention:

    * **A blank name.** PSX publishes no sector for several dozen symbols. That
      is missing upstream data, not something a mapping can fix, so it logs at
      debug level - warning per row buried the real signal in noise.
    * **A name we do not recognise.** PSX has added a sector, and the mapping
      above needs a line. Worth a warning, because until it is added those
      companies are compared against a meaningless peer group.
    """
    name = str(psx_sector_name or "").strip().upper()
    if not name:
        logger.debug("PSX publishes no sector for a listed symbol; using OTHER.")
        return Sector.OTHER
    sector = _SECTOR_BY_PSX_NAME.get(name)
    if sector is None:
        logger.warning(
            "Unmapped PSX sector %r - falling back to OTHER. Peer comparison for "
            "these companies will be against the OTHER bucket, so add the mapping.",
            name,
        )
        return Sector.OTHER
    return sector


class PsxDataProvider:
    """Real PSX data, composed from ``psxdata`` and the PSX company pages.

    Implements :class:`~app.providers.base.MarketDataProvider`. Every upstream
    failure is re-raised as :class:`~app.core.errors.ProviderError` so callers
    handle one exception type and never see a ``requests`` or ``pandas`` error
    leak through the seam.

    ``psxdata`` is imported lazily inside the methods that need it. It pulls in
    pandas, pyarrow and numpy - about 50 MB and a noticeable import cost - and
    the seeded provider is what the test suite and a default checkout use, so
    paying that at process start for everyone would be wrong.
    """

    def __init__(self, *, include_gem: bool = False, http_timeout: float | None = None) -> None:
        #: The Growth Enterprise Market lists small companies under relaxed
        #: disclosure rules. Excluded by default: thin data and thin liquidity
        #: are exactly the conditions the guide warns a beginner away from.
        self._include_gem = include_gem
        self._http_timeout = http_timeout or _HTTP_TIMEOUT_SECONDS

    # -- Protocol ---------------------------------------------------------

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name="psx",
            description=(
                "Real PSX data. Listings and daily OHLCV via the psxdata library; annual "
                "sales, profit after taxation and EPS from the PSX Data Portal company "
                "pages. Balance-sheet and cash-flow figures are not published by either "
                "source, so those checks report insufficient data. Prices are unadjusted "
                "for bonus issues and splits, and quotes are delayed by at least fifteen "
                "minutes - real-time PSX data requires a licence from the exchange."
            ),
            is_synthetic=False,
            verification_sources=[
                "PSX filings and announcements (PUCARS) - https://dps.psx.com.pk/",
                "Sarmaaya - https://sarmaaya.pk/",
                "SCSTrade - https://www.scstrade.com/",
                "Company annual and quarterly reports",
            ],
            # The upstream screener is cached for fifteen minutes, so that is the
            # floor on staleness, not an estimate of it. Real-time PSX data needs a
            # licence from the exchange; claiming 0 here would be a lie the UI would
            # faithfully repeat.
            price_delay_minutes=15,
        )

    def list_companies(self) -> Sequence[CompanyRecord]:
        """Every tradable equity on PSX, with its name and sector.

        Filters the raw 1,000-plus symbol list down to ordinary shares. Term
        Finance Certificates, Sukuks and other debt instruments are excluded
        because a fundamentals checklist built on EPS and profit margins is
        meaningless for them, and ETFs are excluded for the same reason - a fund
        has no revenue of its own to grow.
        """
        frame = self._symbols_frame()
        records: list[CompanyRecord] = []
        for row in frame.to_dict("records"):
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            if bool(row.get("is_debt")) or bool(row.get("is_etf")):
                continue
            if bool(row.get("is_gem")) and not self._include_gem:
                continue
            name = str(row.get("name") or "").strip() or symbol
            records.append(
                CompanyRecord(
                    symbol=symbol,
                    name=name,
                    sector=_sector_for(row.get("sector_name")),
                )
            )
        records.sort(key=lambda record: record.symbol)
        logger.info("PSX listing: %d equities of %d raw symbols", len(records), len(frame))
        return records

    def fetch_price_history(self, symbol: str, sessions: int = 400) -> Sequence[PriceBarRecord]:
        """Up to ``sessions`` daily bars, oldest first.

        ``psxdata`` returns newest-first; the protocol promises oldest-first and
        every indicator depends on that order, so the sort is not cosmetic.
        """
        if sessions <= 0:
            return []
        symbol = symbol.strip().upper()
        start = date.today() - timedelta(days=int(sessions * _CALENDAR_DAYS_PER_SESSION) + 10)
        frame = self._stocks_frame(symbol, start)
        if frame is None or frame.empty:
            return []

        bars: list[PriceBarRecord] = []
        anomalies = 0
        for row in frame.to_dict("records"):
            trade_date = self._as_date(row.get("date"))
            close = _to_decimal(row.get("close"))
            if trade_date is None or close is None:
                # A bar with no date or no close cannot be positioned on a chart
                # or used in an average. Skipping beats inventing a value.
                continue
            open_ = _to_decimal(row.get("open")) or close
            # PSX omits high/low on some historical rows. Falling back to the
            # close keeps the record valid and is harmless here: no engine in
            # app/analysis computes on high or low - they are stored for display
            # and for whatever a future indicator needs.
            high = _to_decimal(row.get("high")) or close
            low = _to_decimal(row.get("low")) or close
            volume = _to_decimal(row.get("volume"))
            if bool(row.get("is_anomaly")):
                anomalies += 1
            bars.append(
                PriceBarRecord(
                    trade_date=trade_date,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=int(volume) if volume is not None else 0,
                )
            )

        bars.sort(key=lambda bar: bar.trade_date)
        if anomalies:
            # Kept, not dropped. psxdata flags bars whose move looks extreme,
            # which is often a real corporate action rather than bad data, and
            # deleting sessions would quietly shorten every moving-average
            # window that spans them.
            logger.warning(
                "%s: %d of %d bars flagged as anomalous upstream (kept; often a "
                "bonus issue or split, since PSX prices are unadjusted).",
                symbol,
                anomalies,
                len(bars),
            )
        return bars[-sessions:]

    def fetch_financials(self, symbol: str) -> Sequence[FinancialsRecord]:
        """Annual sales, profit after taxation and EPS, oldest fiscal year first.

        Returns an empty sequence when the company page has no annual table -
        newly listed companies and some funds genuinely have none, and the
        analysis layer reports that honestly.
        """
        symbol = symbol.strip().upper()
        html = self._company_page_html(symbol)
        if html is None:
            return []
        return _annual_financials(html, symbol=symbol)

    # -- Beyond the protocol ----------------------------------------------

    def fetch_quote(self, symbol: str) -> Quote | None:
        """The most recent screener snapshot for ``symbol``, or ``None``.

        Not part of :class:`MarketDataProvider`: the protocol covers the data
        that gets *synced* into the database, whereas this exists to answer "how
        current is the price I am looking at" without a full re-sync.
        """
        symbol = symbol.strip().upper()
        psxdata = self._psxdata()
        try:
            frame = psxdata.quote(symbol)
        except Exception as exc:
            raise ProviderError(
                "Could not read the current quote from PSX.",
                details={"symbol": symbol, "cause": str(exc)},
            ) from exc
        if frame is None or frame.empty:
            return None
        row = frame.to_dict("records")[0]
        price = _to_decimal(row.get("price"))
        if price is None:
            return None
        return Quote(
            symbol=symbol,
            price=price,
            observed_at=utcnow(),
            change_pct=_as_float(row.get("change_pct")),
            pe_ratio=_as_float(row.get("pe_ratio")),
            dividend_yield=_as_float(row.get("dividend_yield")),
            volume_avg_30d=_as_int(row.get("volume_avg_30d")),
        )

    # -- Upstream access, isolated for testing ----------------------------

    def _psxdata(self) -> Any:
        """Import ``psxdata`` on first use, as a clear error if it is absent."""
        try:
            import psxdata
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ProviderError(
                "The 'psxdata' package is required by the 'psx' market data provider. "
                "Install it with: pip install -e '.[psx]'",
                details={"provider": "psx"},
            ) from exc
        return psxdata

    def _symbols_frame(self) -> pd.DataFrame:
        psxdata = self._psxdata()
        try:
            frame = psxdata.symbols()
        except Exception as exc:
            raise ProviderError(
                "Could not read the PSX symbol list.",
                details={"cause": str(exc)},
            ) from exc
        if frame is None or frame.empty:
            raise ProviderError(
                "PSX returned an empty symbol list. Refusing to treat that as "
                "'no companies exist', which would delete the local universe.",
            )
        return frame

    def _stocks_frame(self, symbol: str, start: date) -> pd.DataFrame | None:
        psxdata = self._psxdata()
        try:
            return psxdata.stocks(symbol, start=start)
        except Exception as exc:
            raise ProviderError(
                "Could not read price history from PSX.",
                details={"symbol": symbol, "start": start.isoformat(), "cause": str(exc)},
            ) from exc

    def _company_page_html(self, symbol: str) -> str | None:
        """Fetch a company page, or ``None`` when PSX has no such page."""
        import requests

        url = COMPANY_PAGE_URL.format(symbol=symbol)
        try:
            response = requests.get(url, headers=_HTTP_HEADERS, timeout=self._http_timeout)
        except requests.RequestException as exc:
            raise ProviderError(
                "Could not reach the PSX company page.",
                details={"symbol": symbol, "url": url, "cause": str(exc)},
            ) from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise ProviderError(
                "The PSX company page returned an unexpected status.",
                details={"symbol": symbol, "url": url, "status": response.status_code},
            )
        return response.text

    @staticmethod
    def _as_date(raw: Any) -> date | None:
        """Coerce a pandas timestamp, ``date`` or ISO string to a ``date``."""
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw.date()
        if isinstance(raw, date):
            return raw
        text = str(raw).strip()
        if not text or text in {"nan", "NaT"}:
            return None
        try:
            return datetime.fromisoformat(text[:10]).date()
        except ValueError:
            return None


def _as_float(raw: Any) -> float | None:
    value = _to_decimal(raw)
    return float(value) if value is not None else None


def _as_int(raw: Any) -> int | None:
    value = _to_decimal(raw)
    return int(value) if value is not None else None


def _implied_shares(net_profit: Decimal | None, eps: Decimal | None) -> Decimal | None:
    """Share count implied by ``net_profit / eps``, or ``None``.

    Neither upstream publishes shares outstanding, but basic EPS is by definition
    profit over the weighted-average share count, so this recovers it. Worth
    doing rather than leaving blank because it is the only way to *see* the
    corporate actions that PSX's unadjusted EPS series hides: Lucky Cement's
    pages imply 319 million shares in FY2023 and 1.49 billion in FY2024, which
    is a bonus issue, not a collapse in per-share earnings.

    Derived, not reported - a reader comparing this against a balance sheet may
    find a small difference, since the weighted average over a year is not the
    count on the year-end date. Guarded against a zero or negative EPS, where the
    division is either undefined or would imply a negative share count.
    """
    if net_profit is None or eps is None or eps <= 0:
        return None
    return net_profit / eps


def _column_value(
    by_field: dict[str, list[Decimal | None]], field: str, index: int
) -> Decimal | None:
    """One cell of the annual table, or ``None`` when row or column is absent.

    A short column is normal: PSX sometimes reports EPS for fewer years than
    sales, and the header row is the authority on how many years the table
    covers. Module level rather than a closure so it captures nothing.
    """
    column = by_field.get(field)
    if column is None or index >= len(column):
        return None
    return column[index]


def _annual_financials(html: str, *, symbol: str) -> list[FinancialsRecord]:
    """Extract the annual figures table from a PSX company page.

    The page carries several tables with the same markup - directors, filings,
    board meetings, an annual table, a quarterly table and a ratios table - and
    none of them is labelled with an id or a stable class. This identifies the
    annual one structurally: its header row is a blank corner cell followed by
    four-digit years, which the quarterly table (``Q3 2026``) fails and the
    filings tables (``Date``, ``Title``) fail too.

    On EPS: the figures are **as reported**, and PSX does not restate them for
    bonus issues. Lucky Cement's page shows EPS 43.06 for 2023 against a profit
    a third of 2024's, because the share count changed. The trend check is
    therefore comparing different share bases across a corporate action, which
    is a property of the source, not something this parser can repair - it would
    need a shares-outstanding history nobody here publishes. Recorded here so
    the next reader does not mistake it for a parsing bug.
    """
    import bs4

    soup = bs4.BeautifulSoup(html, "lxml")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        header = [cell.get_text(strip=True) for cell in rows[0].find_all(["th", "td"])]
        if len(header) < 3 or header[0]:
            # The annual table's corner cell is empty; a filings table starts
            # with "Date" and the quarterly table's columns are "Q3 2026".
            continue
        years: list[int] = []
        for text in header[1:]:
            if not re.fullmatch(r"\d{4}", text):
                years = []
                break
            years.append(int(text))
        if not years:
            continue

        by_field: dict[str, list[Decimal | None]] = {}
        for row in rows[1:]:
            cells = [cell.get_text(strip=True) for cell in row.find_all(["th", "td"])]
            if len(cells) < 2:
                continue
            label = cells[0].strip().lower().rstrip(":")
            for field, aliases in _ANNUAL_ROW_LABELS.items():
                if label in aliases and field not in by_field:
                    # Only EPS is already per-share; the rest are in thousands.
                    scale = Decimal(1) if field == "eps" else _THOUSANDS
                    by_field[field] = [
                        _to_decimal(cell, scale=scale) for cell in cells[1 : len(years) + 1]
                    ]
        if not by_field:
            continue

        records: list[FinancialsRecord] = []
        for index, fiscal_year in enumerate(years):
            revenue = _column_value(by_field, "revenue", index)
            net_profit = _column_value(by_field, "net_profit", index)
            eps = _column_value(by_field, "eps", index)
            if revenue is None and net_profit is None and eps is None:
                continue
            records.append(
                FinancialsRecord(
                    fiscal_year=fiscal_year,
                    revenue=revenue,
                    net_profit=net_profit,
                    eps=eps,
                    shares_outstanding=_implied_shares(net_profit, eps),
                    # Deliberately absent: neither upstream publishes the
                    # balance sheet or the cash flow statement. See the module
                    # docstring - these become INSUFFICIENT_DATA verdicts, not
                    # zeroes.
                    source=COMPANY_PAGE_URL.format(symbol=symbol),
                )
            )
        # Oldest fiscal year first, as the protocol requires: the page lists the
        # most recent year in the leftmost column.
        records.sort(key=lambda record: record.fiscal_year)
        if records:
            return records
    logger.info("%s: no annual figures table on the PSX company page.", symbol)
    return []
