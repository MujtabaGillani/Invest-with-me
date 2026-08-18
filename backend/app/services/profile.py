"""Investor profile service - guide section 1.

Also the home of the *effective* profile: the limits used for sizing and
concentration checks when a user has not written a profile yet. Those defaults
are conservative on purpose. A user who has not declared a risk limit should not
be treated as having a generous one.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.enums import RiskTolerance, TimeHorizon
from app.models.investor_profile import InvestorProfile
from app.repositories.users import InvestorProfileRepository
from app.schemas.profile import InvestorProfileRead, InvestorProfileUpsert


class ProfileService:
    """Read and write the user's investment plan."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.profiles = InvestorProfileRepository(session)

    # -- Reads -------------------------------------------------------------

    def get_effective(self, user_id: int) -> InvestorProfile:
        """The user's profile, or an unsaved conservative default.

        Returned as a transient :class:`InvestorProfile` (never added to the
        session) so every caller can rely on the same attributes without a
        ``None`` check or a parallel "defaults" object. It is deliberately not
        persisted: an auto-created profile would look, to the user, as though they
        had already written down goals they never chose.
        """
        existing = self.profiles.get_for_user(user_id)
        if existing is not None:
            return existing
        return InvestorProfile(
            user_id=user_id,
            time_horizon=TimeHorizon.LONG_TERM,
            risk_tolerance=RiskTolerance.MODERATE,
            drawdown_tolerance_pct=Decimal("30"),
            investable_capital=Decimal("0"),
            max_position_pct=Decimal("15"),
            max_sector_pct=Decimal("35"),
            emergency_fund_in_place=False,
            investing_borrowed_money=False,
            review_interval_days=90,
        )

    def has_profile(self, user_id: int) -> bool:
        """Whether the user has actually written a profile."""
        return self.profiles.get_for_user(user_id) is not None

    def read(self, user_id: int) -> InvestorProfileRead | None:
        """The stored profile with derived warnings, or ``None`` if unwritten."""
        profile = self.profiles.get_for_user(user_id)
        if profile is None:
            return None
        return self._to_read_model(profile)

    # -- Writes ------------------------------------------------------------

    def upsert(self, user_id: int, payload: InvestorProfileUpsert) -> InvestorProfileRead:
        """Create or replace the user's profile.

        Commits, because writing the profile is a complete unit of work initiated
        directly by the user.
        """
        profile = self.profiles.get_for_user(user_id)
        if profile is None:
            profile = InvestorProfile(user_id=user_id)
            self.session.add(profile)

        profile.time_horizon = payload.time_horizon
        profile.risk_tolerance = payload.risk_tolerance
        profile.drawdown_tolerance_pct = payload.drawdown_tolerance_pct
        profile.investable_capital = payload.investable_capital
        profile.max_position_pct = payload.max_position_pct
        profile.max_sector_pct = payload.max_sector_pct
        profile.emergency_fund_in_place = payload.emergency_fund_in_place
        profile.investing_borrowed_money = payload.investing_borrowed_money
        profile.review_interval_days = payload.review_interval_days
        profile.goals_note = payload.goals_note

        self.session.commit()
        self.session.refresh(profile)
        return self._to_read_model(profile)

    # -- Internals ---------------------------------------------------------

    def _to_read_model(self, profile: InvestorProfile) -> InvestorProfileRead:
        return InvestorProfileRead(
            time_horizon=profile.time_horizon,
            risk_tolerance=profile.risk_tolerance,
            drawdown_tolerance_pct=profile.drawdown_tolerance_pct,
            investable_capital=profile.investable_capital,
            max_position_pct=profile.max_position_pct,
            max_sector_pct=profile.max_sector_pct,
            emergency_fund_in_place=profile.emergency_fund_in_place,
            investing_borrowed_money=profile.investing_borrowed_money,
            review_interval_days=profile.review_interval_days,
            goals_note=profile.goals_note,
            warnings=build_profile_warnings(profile),
        )


def build_profile_warnings(profile: InvestorProfile) -> list[str]:
    """Concerns the guide's section 1 would raise about this profile.

    A pure function of the profile, so it can be unit-tested and so the same
    warnings appear wherever a profile is shown. Ordered most serious first.

    Note what is *not* here: nothing tells the user their answers are wrong. Each
    warning states a consequence they may not have connected to the choice they
    made, which is the difference between informing and instructing.
    """
    warnings: list[str] = []

    if profile.investing_borrowed_money:
        warnings.append(
            "You have recorded that some of this money is borrowed. A market fall then costs you "
            "the loss and the interest, and the repayment schedule decides when you sell rather "
            "than your own plan."
        )

    if not profile.emergency_fund_in_place:
        warnings.append(
            "No emergency fund is recorded. Money you might need at short notice tends to get "
            "withdrawn at the worst possible moment - the guide's rule is to invest only what "
            "you can afford to leave alone."
        )

    if profile.investable_capital <= 0:
        warnings.append(
            "No investable capital is recorded, so position sizing has nothing to size against. "
            "Set it to make the pre-buy checks meaningful."
        )

    if profile.time_horizon is TimeHorizon.SHORT_TERM:
        warnings.append(
            "You have recorded a short-term horizon. Short-term trading and long-term investing "
            "are different skills with different risk levels; the fundamentals checklist in this "
            "tool is built for the latter."
        )

    if profile.drawdown_tolerance_pct < Decimal("20"):
        warnings.append(
            f"You recorded that a fall of more than {profile.drawdown_tolerance_pct:g}% would be "
            "hard to hold through. Individual PSX stocks routinely move more than that, so expect "
            "to be tested at this level of tolerance."
        )

    aggressive_but_cautious = profile.risk_tolerance is RiskTolerance.AGGRESSIVE and (
        profile.drawdown_tolerance_pct < Decimal("25")
    )
    if aggressive_but_cautious:
        warnings.append(
            "You describe your risk tolerance as aggressive but your stated drawdown tolerance is "
            "low. Those two answers pull in opposite directions - worth deciding which is the "
            "honest one before you buy."
        )

    if profile.max_position_pct > Decimal("25"):
        warnings.append(
            f"A single holding may take up to {profile.max_position_pct:g}% of your portfolio "
            "under your current limit. That concentrates a lot of the outcome into one company's "
            "results."
        )

    if profile.review_interval_days > 180:
        warnings.append(
            f"You plan to revisit each holding only every {profile.review_interval_days} days. A "
            "thesis can break well inside that window."
        )

    return warnings
