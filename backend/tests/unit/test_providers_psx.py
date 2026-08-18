"""Unit tests for the real PSX provider.

**No network, and no PSX data committed to this repo.** The HTML fixtures below
are hand-written to reproduce the *structure* of a PSX company page - the same
table markup, the same thousands-and-parentheses number formats, the same
unlabelled tables in the same order - with invented figures. Two reasons:

1. PSX prohibits redistributing its market data, and a saved copy of a real page
   is exactly that.
2. A fixture with invented numbers makes the assertions readable. ``1,000`` in
   becomes ``1_000_000`` out, and a reader can check the scaling by eye.

``psxdata`` is faked rather than imported, so the suite never depends on the
optional ``[psx]`` extra (pandas, pyarrow, numpy) and never hits the network.
The fake implements only the three attributes the provider actually uses -
``.empty``, ``.to_dict("records")`` and ``len()`` - which also documents how
narrow the coupling to pandas is.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.core.enums import Sector
from app.core.errors import ProviderError
from app.providers.base import MarketDataProvider
from app.providers.psx import (
    PsxDataProvider,
    _annual_financials,
    _implied_shares,
    _sector_for,
    _to_decimal,
)


class FakeFrame:
    """The slice of the pandas DataFrame API that the provider relies on."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    @property
    def empty(self) -> bool:
        return not self._rows

    def to_dict(self, _orient: str) -> list[dict[str, Any]]:
        return list(self._rows)

    def __len__(self) -> int:
        return len(self._rows)


class FakePsxData:
    """Stands in for the ``psxdata`` module."""

    def __init__(
        self,
        *,
        symbols_rows: list[dict[str, Any]] | None = None,
        stocks_rows: list[dict[str, Any]] | None = None,
        quote_rows: list[dict[str, Any]] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._symbols_rows = symbols_rows or []
        self._stocks_rows = stocks_rows or []
        self._quote_rows = quote_rows or []
        self._raises = raises
        self.stocks_calls: list[tuple[str, date]] = []

    def symbols(self) -> FakeFrame:
        if self._raises:
            raise self._raises
        return FakeFrame(self._symbols_rows)

    def stocks(self, symbol: str, start: date | None = None, **_: Any) -> FakeFrame:
        if self._raises:
            raise self._raises
        assert start is not None
        self.stocks_calls.append((symbol, start))
        return FakeFrame(self._stocks_rows)

    def quote(self, _symbol: str, **_kwargs: Any) -> FakeFrame:
        if self._raises:
            raise self._raises
        return FakeFrame(self._quote_rows)


def build_provider(fake: FakePsxData, **kwargs: Any) -> PsxDataProvider:
    """A provider whose only upstream is ``fake``."""
    provider = PsxDataProvider(**kwargs)
    provider._psxdata = lambda: fake  # type: ignore[method-assign]
    return provider


# --- Number parsing --------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("136,527,017", Decimal("136527017")),  # thousands separators
        ("(56.08)", Decimal("-56.08")),  # accounting negative
        ("Rs.439.30", Decimal("439.30")),  # price prefix
        ("34.15%", Decimal("34.15")),  # percentage suffix
        ("31.83", Decimal("31.83")),
        ("0", Decimal("0")),
    ],
)
def test_to_decimal_parses_psx_number_formats(raw: str, expected: Decimal) -> None:
    assert _to_decimal(raw) == expected


@pytest.mark.parametrize("raw", ["", "  ", "-", "--", "N/A", "n/a", "nan", "NaN", None, "abc"])
def test_to_decimal_returns_none_for_missing_figures(raw: Any) -> None:
    """A missing figure must never become ``0``.

    Zero revenue or zero equity would be *scored* by the analysis engines as a
    genuinely terrible result, whereas ``None`` reaches them as
    INSUFFICIENT_DATA. This is the single most important behaviour in the parser.
    """
    assert _to_decimal(raw) is None


def test_to_decimal_applies_scale_to_thousands() -> None:
    assert _to_decimal("1,000", scale=Decimal(1000)) == Decimal("1000000")


# --- Sector mapping -------------------------------------------------------


@pytest.mark.parametrize(
    ("psx_name", "expected"),
    [
        ("CEMENT", Sector.CEMENT),
        ("cement", Sector.CEMENT),  # case-insensitive
        ("COMMERCIAL BANKS", Sector.COMMERCIAL_BANKS),
        ("OIL & GAS EXPLORATION COMPANIES", Sector.OIL_AND_GAS),
        ("OIL & GAS MARKETING COMPANIES", Sector.OIL_AND_GAS_MARKETING),
        ("INV. BANKS / INV. COS. / SECURITIES COS.", Sector.INVESTMENT_BANKS),
        ("SUGAR & ALLIED INDUSTRIES", Sector.SUGAR),
    ],
)
def test_sector_mapping(psx_name: str, expected: Sector) -> None:
    assert _sector_for(psx_name) is expected


def test_exploration_and_marketing_are_not_the_same_sector() -> None:
    """The split is the point: peer-relative P/E depends on it.

    A driller and a fuel retailer trade on different multiples for different
    reasons, so folding them together would make the comparison misleading.
    """
    assert _sector_for("OIL & GAS EXPLORATION COMPANIES") is not _sector_for(
        "OIL & GAS MARKETING COMPANIES"
    )


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_sector_is_other_without_warning(
    blank: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """PSX omits the sector for dozens of symbols; that is not a mapping gap."""
    with caplog.at_level("WARNING"):
        assert _sector_for(blank) is Sector.OTHER
    assert not caplog.records


def test_unknown_sector_warns_so_the_mapping_gets_extended(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        assert _sector_for("QUANTUM WIDGETS") is Sector.OTHER
    assert any("Unmapped PSX sector" in record.message for record in caplog.records)


# --- Implied share count --------------------------------------------------


def test_implied_shares_recovers_the_share_count() -> None:
    assert _implied_shares(Decimal("1000"), Decimal("2")) == Decimal("500")


@pytest.mark.parametrize(
    ("profit", "eps"),
    [
        (Decimal("1000"), Decimal("0")),  # division undefined
        (Decimal("-500"), Decimal("-2")),  # loss-maker: would imply +250 shares
        (None, Decimal("2")),
        (Decimal("1000"), None),
    ],
)
def test_implied_shares_declines_to_guess(profit: Decimal | None, eps: Decimal | None) -> None:
    assert _implied_shares(profit, eps) is None


# --- Company page parsing -------------------------------------------------

#: Reproduces a PSX company page: a directors table, a filings table, a
#: *quarterly* table and the annual table - none labelled, all identical markup.
#: The parser must pick the annual one out of that, so the decoys are the test.
COMPANY_PAGE_HTML = """
<html><body>
  <table><tr><td>A. Person</td><td>CEO</td></tr></table>
  <table>
    <tr><th>Date</th><th>Title</th><th>Document</th></tr>
    <tr><td>Aug 10, 2026</td><td>Financial Results</td><td>View</td></tr>
  </table>
  <table>
    <tr><th></th><th>Q3 2026</th><th>Q2 2026</th><th>Q1 2026</th></tr>
    <tr><td>Sales</td><td>9,000</td><td>8,000</td><td>7,000</td></tr>
    <tr><td>EPS</td><td>1.00</td><td>2.00</td><td>3.00</td></tr>
  </table>
  <table>
    <tr><th></th><th>2026</th><th>2025</th><th>2024</th></tr>
    <tr><td>Sales</td><td>3,000</td><td>2,000</td><td>1,000</td></tr>
    <tr><td>Profit after Taxation</td><td>300</td><td>200</td><td>(50)</td></tr>
    <tr><td>EPS</td><td>3.00</td><td>2.00</td><td>(0.50)</td></tr>
  </table>
</body></html>
"""


def test_annual_financials_picks_the_annual_table_not_the_quarterly_one() -> None:
    records = _annual_financials(COMPANY_PAGE_HTML, symbol="TEST")
    assert [record.fiscal_year for record in records] == [2024, 2025, 2026], (
        "must be oldest fiscal year first, and must not have matched 'Q3 2026'"
    )


def test_annual_financials_scales_thousands_but_not_eps() -> None:
    latest = _annual_financials(COMPANY_PAGE_HTML, symbol="TEST")[-1]
    assert latest.revenue == Decimal("3000000")  # 3,000 thousand
    assert latest.net_profit == Decimal("300000")
    assert latest.eps == Decimal("3.00")  # already per share


def test_annual_financials_keeps_accounting_negatives() -> None:
    oldest = _annual_financials(COMPANY_PAGE_HTML, symbol="TEST")[0]
    assert oldest.net_profit == Decimal("-50000")
    assert oldest.eps == Decimal("-0.50")


def test_annual_financials_leaves_unpublished_fields_absent() -> None:
    """Balance sheet and cash flow are not on the page; they must stay ``None``."""
    latest = _annual_financials(COMPANY_PAGE_HTML, symbol="TEST")[-1]
    assert latest.total_equity is None
    assert latest.total_debt is None
    assert latest.total_assets is None
    assert latest.operating_cash_flow is None
    assert latest.capital_expenditure is None
    assert latest.dividend_per_share is None


def test_annual_financials_records_its_source() -> None:
    latest = _annual_financials(COMPANY_PAGE_HTML, symbol="TEST")[-1]
    assert latest.source == "https://dps.psx.com.pk/company/TEST"


def test_annual_financials_derives_shares_outstanding() -> None:
    latest = _annual_financials(COMPANY_PAGE_HTML, symbol="TEST")[-1]
    assert latest.shares_outstanding == Decimal("100000")  # 300,000 / 3.00


@pytest.mark.parametrize(
    "html",
    [
        "<html><body></body></html>",
        "<html><body><table><tr><th>Date</th><th>Title</th></tr></table></body></html>",
        # Year headers but no row we recognise.
        "<html><body><table><tr><th></th><th>2026</th><th>2025</th></tr>"
        "<tr><td>Something Else</td><td>1</td><td>2</td></tr></table></body></html>",
    ],
)
def test_annual_financials_returns_empty_when_there_is_no_annual_table(html: str) -> None:
    """No filings is a normal outcome for a new listing, not an error."""
    assert _annual_financials(html, symbol="TEST") == []


# --- list_companies -------------------------------------------------------


SYMBOL_ROWS: list[dict[str, Any]] = [
    {"symbol": "LUCK", "name": "Lucky Cement Limited", "sector_name": "CEMENT"},
    {"symbol": "HBL", "name": "Habib Bank Limited", "sector_name": "COMMERCIAL BANKS"},
    {
        "symbol": "ABCTFC6",
        "name": "Some Bank (TFC6)",
        "sector_name": "BILLS AND BONDS",
        "is_debt": True,
    },
    {"symbol": "MEETF", "name": "An ETF", "sector_name": "EXCHANGE TRADED FUNDS", "is_etf": True},
    {"symbol": "GEMCO", "name": "Small Co", "sector_name": "ENGINEERING", "is_gem": True},
]


def test_list_companies_excludes_debt_and_etfs() -> None:
    """A fundamentals checklist built on EPS is meaningless for a TFC or a fund."""
    provider = build_provider(FakePsxData(symbols_rows=SYMBOL_ROWS))
    symbols = [company.symbol for company in provider.list_companies()]
    assert symbols == ["HBL", "LUCK"], "sorted, equities only"


def test_list_companies_excludes_gem_by_default_and_includes_it_on_request() -> None:
    rows = FakePsxData(symbols_rows=SYMBOL_ROWS)
    assert "GEMCO" not in [c.symbol for c in build_provider(rows).list_companies()]
    included = build_provider(FakePsxData(symbols_rows=SYMBOL_ROWS), include_gem=True)
    assert "GEMCO" in [company.symbol for company in included.list_companies()]


def test_list_companies_maps_sector_and_falls_back_to_symbol_for_a_blank_name() -> None:
    provider = build_provider(
        FakePsxData(symbols_rows=[{"symbol": "xyz", "name": "  ", "sector_name": "CEMENT"}])
    )
    company = provider.list_companies()[0]
    assert company.symbol == "XYZ", "symbols are upper-cased"
    assert company.name == "XYZ"
    assert company.sector is Sector.CEMENT


def test_list_companies_rejects_an_empty_upstream_list() -> None:
    """An empty response must not be read as 'PSX has no listings'.

    The sync replaces the local universe from this list, so silently accepting
    an empty one during an upstream outage would wipe it.
    """
    provider = build_provider(FakePsxData(symbols_rows=[]))
    with pytest.raises(ProviderError, match="empty symbol list"):
        provider.list_companies()


# --- fetch_price_history --------------------------------------------------


PRICE_ROWS: list[dict[str, Any]] = [
    # Newest first, as psxdata returns them.
    {
        "date": "2026-08-18",
        "open": 443.40,
        "high": 444.0,
        "low": 438.0,
        "close": 439.30,
        "volume": 1250095,
    },
    {
        "date": "2026-08-17",
        "open": 448.01,
        "high": 449.4,
        "low": 442.0,
        "close": 443.37,
        "volume": 753981,
    },
    {
        "date": "2026-08-13",
        "open": 447.88,
        "high": 450.0,
        "low": 445.0,
        "close": 446.61,
        "volume": 696125,
    },
]


def test_fetch_price_history_returns_oldest_first() -> None:
    """Every indicator depends on this order, so the sort is not cosmetic."""
    bars = build_provider(FakePsxData(stocks_rows=PRICE_ROWS)).fetch_price_history("LUCK")
    assert [bar.trade_date for bar in bars] == [
        date(2026, 8, 13),
        date(2026, 8, 17),
        date(2026, 8, 18),
    ]


def test_fetch_price_history_converts_to_decimal() -> None:
    latest = build_provider(FakePsxData(stocks_rows=PRICE_ROWS)).fetch_price_history("LUCK")[-1]
    assert latest.close == Decimal("439.3")
    assert isinstance(latest.close, Decimal)
    assert latest.volume == 1250095


def test_fetch_price_history_falls_back_to_close_for_a_missing_high_or_low() -> None:
    rows = [{"date": "2026-08-18", "close": 100.0, "volume": 5}]
    bar = build_provider(FakePsxData(stocks_rows=rows)).fetch_price_history("LUCK")[0]
    assert (bar.open, bar.high, bar.low) == (Decimal("100"), Decimal("100"), Decimal("100"))


def test_fetch_price_history_skips_bars_with_no_date_or_no_close() -> None:
    rows: list[dict[str, Any]] = [
        {"date": "2026-08-18", "close": 100.0, "volume": 5},
        {"date": None, "close": 101.0, "volume": 5},
        {"date": "2026-08-17", "close": None, "volume": 5},
    ]
    bars = build_provider(FakePsxData(stocks_rows=rows)).fetch_price_history("LUCK")
    assert len(bars) == 1


def test_fetch_price_history_truncates_to_the_requested_sessions() -> None:
    bars = build_provider(FakePsxData(stocks_rows=PRICE_ROWS)).fetch_price_history(
        "LUCK", sessions=2
    )
    assert [bar.trade_date for bar in bars] == [date(2026, 8, 17), date(2026, 8, 18)], (
        "keeps the most recent sessions, not the oldest"
    )


def test_fetch_price_history_requests_a_wide_enough_window() -> None:
    """Under-fetching would silently shorten a 200-day moving average."""
    fake = FakePsxData(stocks_rows=PRICE_ROWS)
    build_provider(fake).fetch_price_history("LUCK", sessions=200)
    _symbol, start = fake.stocks_calls[0]
    assert (date.today() - start).days > 200 * 1.5


@pytest.mark.parametrize("sessions", [0, -5])
def test_fetch_price_history_returns_nothing_for_a_non_positive_session_count(
    sessions: int,
) -> None:
    fake = FakePsxData(stocks_rows=PRICE_ROWS)
    assert build_provider(fake).fetch_price_history("LUCK", sessions=sessions) == []
    assert not fake.stocks_calls, "must not call upstream at all"


def test_fetch_price_history_is_empty_for_an_unknown_symbol() -> None:
    assert build_provider(FakePsxData(stocks_rows=[])).fetch_price_history("NOPE") == []


# --- Quotes ---------------------------------------------------------------


def test_fetch_quote_stamps_the_observation_time_and_the_delay() -> None:
    """The age is part of the value: a delayed price presented as current lies."""
    rows = [
        {
            "symbol": "LUCK",
            "price": 439.30,
            "change_pct": -0.92,
            "pe_ratio": 13.8,
            "dividend_yield": 1.06,
            "volume_avg_30d": 1914309.0,
        }
    ]
    quote = build_provider(FakePsxData(quote_rows=rows)).fetch_quote("LUCK")
    assert quote is not None
    assert quote.price == Decimal("439.3")
    assert quote.observed_at.tzinfo is not None, "timestamps are timezone-aware UTC"
    assert isinstance(quote.observed_at, datetime)
    assert quote.delay_minutes >= 15
    assert quote.pe_ratio == pytest.approx(13.8)
    assert quote.volume_avg_30d == 1914309


def test_fetch_quote_is_none_when_there_is_no_price() -> None:
    provider = build_provider(FakePsxData(quote_rows=[{"symbol": "LUCK", "price": None}]))
    assert provider.fetch_quote("LUCK") is None


def test_fetch_quote_is_none_for_an_unknown_symbol() -> None:
    assert build_provider(FakePsxData(quote_rows=[])).fetch_quote("NOPE") is None


# --- Error normalisation and contract -------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda provider: provider.list_companies(),
        lambda provider: provider.fetch_price_history("LUCK"),
        lambda provider: provider.fetch_quote("LUCK"),
    ],
)
def test_upstream_failures_surface_as_provider_error(call: Any) -> None:
    """Callers handle one exception type; no requests or pandas error leaks out."""
    provider = build_provider(FakePsxData(raises=RuntimeError("upstream exploded")))
    with pytest.raises(ProviderError):
        call(provider)


def test_metadata_does_not_claim_to_be_synthetic() -> None:
    """The flag the UI trusts. A provider that lies here is the worst bug we could ship."""
    metadata = PsxDataProvider().metadata
    assert metadata.is_synthetic is False
    assert metadata.name == "psx"
    assert metadata.verification_sources, "section 8 of the guide: let the user check"


def test_metadata_declares_the_price_delay_rather_than_claiming_real_time() -> None:
    """Unlicensed public PSX data is always behind the market.

    Reporting 0 here would make the UI drop its "delayed prices" notice, which is
    the one thing someone timing a buy or sell needs to see.
    """
    assert PsxDataProvider().metadata.price_delay_minutes == 15


def test_provider_satisfies_the_protocol() -> None:
    assert isinstance(PsxDataProvider(), MarketDataProvider)


def test_registry_exposes_psx_without_importing_pandas() -> None:
    """Selecting the provider by name must work, and only then pay the import cost."""
    from app.providers.registry import available_providers

    assert "psx" in available_providers()
