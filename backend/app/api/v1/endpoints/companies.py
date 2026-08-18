"""Company browsing, raw statements, price history and analysis endpoints.

Analysis lives on the company resource (``/companies/{symbol}/fundamentals``)
rather than under a separate ``/analysis`` tree: a report is a *view of a
company*, and nesting it keeps the URL readable and the client's mental model
simple.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.api.deps import (
    AnalysisServiceDep,
    CompanyServiceDep,
    CurrentUser,
    Pagination,
    ProfileServiceDep,
    SectorFilter,
)
from app.schemas.analysis import FundamentalsReport, TechnicalReport
from app.schemas.common import Page
from app.schemas.company import CompanyDetail, CompanySummary, PriceHistoryRead

router = APIRouter(prefix="/companies", tags=["companies"])

SymbolPath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=16,
        description="PSX ticker symbol, e.g. OGDC. Case-insensitive.",
        examples=["OGDC"],
    ),
]


@router.get(
    "",
    response_model=Page[CompanySummary],
    summary="List companies",
    response_description="A page of companies with their latest stored close.",
)
def list_companies(
    service: CompanyServiceDep,
    pagination: Pagination,
    sector: SectorFilter = None,
    search: Annotated[
        str | None, Query(max_length=100, description="Match against symbol or company name.")
    ] = None,
) -> Page[CompanySummary]:
    """Browse the companies available for analysis."""
    return service.list_companies(
        search=search,
        sector=sector,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get(
    "/{symbol}",
    response_model=CompanyDetail,
    summary="Get one company",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Unknown symbol."}},
)
def get_company(symbol: SymbolPath, service: CompanyServiceDep) -> CompanyDetail:
    """One company with its stored annual figures, exactly as reported.

    Derived ratios are deliberately not included here - see the fundamentals
    endpoint, which explains and judges them.
    """
    return service.get_company_detail(symbol)


@router.get(
    "/{symbol}/prices",
    response_model=PriceHistoryRead,
    summary="Get price history",
)
def get_price_history(
    symbol: SymbolPath,
    service: CompanyServiceDep,
    sessions: Annotated[
        int, Query(ge=2, le=1000, description="Number of most recent sessions to return.")
    ] = 260,
) -> PriceHistoryRead:
    """Daily OHLCV bars, oldest first."""
    return service.get_price_history(symbol, sessions=sessions)


@router.get(
    "/{symbol}/fundamentals",
    response_model=FundamentalsReport,
    summary="Run the fundamentals checklist",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Unknown symbol."},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "No financial statements are stored for this company."
        },
    },
)
def get_fundamentals(symbol: SymbolPath, service: AnalysisServiceDep) -> FundamentalsReport:
    """Score a company against the guide's fundamentals checklist.

    Returns a verdict per metric, the four-question statement review, any red
    flags, and counts of how many criteria are met. It does not return a rating,
    a price target or a buy/sell signal, and it never will - see
    ``docs/ARCHITECTURE.md`` on why that constraint is treated as a requirement.
    """
    return service.fundamentals(symbol)


@router.get(
    "/{symbol}/technicals",
    response_model=TechnicalReport,
    summary="Get technical readings",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Unknown symbol."},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Not enough price history for a technical reading."
        },
    },
)
def get_technicals(
    symbol: SymbolPath,
    service: AnalysisServiceDep,
    profiles: ProfileServiceDep,
    user: CurrentUser,
) -> TechnicalReport:
    """Trend, RSI, moving averages and volume confirmation for one company.

    The user's declared time horizon is read from their profile purely to frame
    the result: the guide's point is that a bearish reading matters far less to a
    five-year holder than to a short-term trader. The numbers are identical either
    way.
    """
    profile = profiles.get_effective(user.id)
    return service.technicals(symbol, horizon=profile.time_horizon)
