"""Investor profile endpoints - guide section 1."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, ProfileServiceDep
from app.schemas.profile import InvestorProfileRead, InvestorProfileUpsert

router = APIRouter(prefix="/profile", tags=["investor profile"])


@router.get(
    "",
    response_model=InvestorProfileRead,
    summary="Get the investor profile",
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "No profile has been written yet - the client should prompt for one."
        }
    },
)
def get_profile(
    service: ProfileServiceDep, user: CurrentUser, response: Response
) -> InvestorProfileRead | Response:
    """Your recorded goals, risk limits and money-hygiene declarations.

    Returns ``204 No Content`` when no profile exists, rather than a 404 or an
    object of defaults. A 404 would suggest something is broken, and returning
    defaults would let the user believe they had already written down goals they
    never chose - the first thing the guide asks them to do.
    """
    profile = service.read(user.id)
    if profile is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return profile


@router.put(
    "",
    response_model=InvestorProfileRead,
    summary="Create or replace the investor profile",
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Limits are incoherent, e.g. a position cap above the sector cap."
        }
    },
)
def upsert_profile(
    payload: InvestorProfileUpsert, service: ProfileServiceDep, user: CurrentUser
) -> InvestorProfileRead:
    """Write down your time horizon, risk tolerance and position limits.

    A full replacement rather than a patch: the guide's instruction is to decide all
    of this together, before looking at any company. The response includes derived
    warnings - for example if no emergency fund is recorded, or if the stated risk
    tolerance and drawdown tolerance contradict each other.
    """
    return service.upsert(user.id, payload)
