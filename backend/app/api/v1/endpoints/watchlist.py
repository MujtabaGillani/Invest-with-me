"""Watchlist endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, status

from app.api.deps import CurrentUser, WatchlistServiceDep
from app.schemas.watchlist import WatchlistItemCreate, WatchlistItemRead, WatchlistItemUpdate

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

ItemIdPath = Annotated[int, Path(ge=1, description="Watchlist entry id.")]


@router.get("", response_model=list[WatchlistItemRead], summary="List watched companies")
def list_watchlist(service: WatchlistServiceDep, user: CurrentUser) -> list[WatchlistItemRead]:
    """Companies you are researching, with a current price snapshot on each.

    ``entry_price_reached`` and ``distance_to_target_pct`` are computed against the
    latest stored close, so the client does not have to replicate the arithmetic.
    """
    return service.list_items(user.id)


@router.post(
    "",
    response_model=WatchlistItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Watch a company",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Unknown symbol."},
        status.HTTP_409_CONFLICT: {"description": "Already on the watchlist."},
    },
)
def add_watchlist_item(
    payload: WatchlistItemCreate, service: WatchlistServiceDep, user: CurrentUser
) -> WatchlistItemRead:
    """Add a company to the watchlist.

    A research note is required. The guide's first listed mistake is chasing hype,
    and having to write down *why* before the app will track something is the
    cheapest available guard against it.
    """
    return service.add_item(user.id, payload)


@router.patch(
    "/{item_id}",
    response_model=WatchlistItemRead,
    summary="Update a watchlist entry",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Entry not found."}},
)
def update_watchlist_item(
    item_id: ItemIdPath,
    payload: WatchlistItemUpdate,
    service: WatchlistServiceDep,
    user: CurrentUser,
) -> WatchlistItemRead:
    """Revise the research note or the entry price you are waiting for."""
    return service.update_item(user.id, item_id, payload)


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop watching a company",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Entry not found."}},
)
def remove_watchlist_item(
    item_id: ItemIdPath, service: WatchlistServiceDep, user: CurrentUser
) -> None:
    """Remove a company from the watchlist."""
    service.remove_item(user.id, item_id)
