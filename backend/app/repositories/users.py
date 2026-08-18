"""User and investor profile queries."""

from __future__ import annotations

from sqlalchemy import select

from app.models.investor_profile import InvestorProfile
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """User lookup and creation."""

    model = User

    def get_by_email(self, email: str) -> User | None:
        """Fetch by email, normalised to lower case."""
        statement = select(User).where(User.email == email.strip().lower())
        return self.session.scalars(statement).one_or_none()

    def get_or_create(self, email: str, display_name: str) -> User:
        """Return the user for ``email``, creating one if absent.

        Used by the single-user dependency at request time. Safe to call
        concurrently only because the unique index on ``email`` would reject a
        duplicate - if that ever fires in production it is a signal that real
        authentication is overdue, not something to paper over with a retry.
        """
        existing = self.get_by_email(email)
        if existing is not None:
            return existing
        return self.add(User(email=email.strip().lower(), display_name=display_name))


class InvestorProfileRepository(BaseRepository[InvestorProfile]):
    """The one-per-user investment plan."""

    model = InvestorProfile

    def get_for_user(self, user_id: int) -> InvestorProfile | None:
        """Fetch a user's profile, or ``None`` if they have not written one yet."""
        statement = select(InvestorProfile).where(InvestorProfile.user_id == user_id)
        return self.session.scalars(statement).one_or_none()
