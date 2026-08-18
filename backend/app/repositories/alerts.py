"""Alert queries."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.models.alert import Alert
from app.repositories.base import BaseRepository


class AlertRepository(BaseRepository[Alert]):
    """Per-user alerts, de-duplicated by ``dedupe_key``."""

    model = Alert

    def list_for_user(
        self, user_id: int, *, include_acknowledged: bool = False, limit: int = 100
    ) -> Sequence[Alert]:
        """Alerts newest first, unacknowledged only by default."""
        statement = (
            select(Alert)
            .where(Alert.user_id == user_id)
            .options(joinedload(Alert.company))
            .order_by(Alert.created_at.desc(), Alert.id.desc())
            .limit(limit)
        )
        if not include_acknowledged:
            statement = statement.where(Alert.acknowledged_at.is_(None))
        return self.session.scalars(statement).unique().all()

    def get_for_user(self, user_id: int, alert_id: int) -> Alert | None:
        """Fetch one alert, scoped to its owner."""
        statement = (
            select(Alert)
            .where(Alert.user_id == user_id, Alert.id == alert_id)
            .options(joinedload(Alert.company))
        )
        return self.session.scalars(statement).one_or_none()

    def open_alerts_by_key(self, user_id: int) -> dict[str, Alert]:
        """Unacknowledged alerts keyed by ``dedupe_key``.

        The monitor loads this once per evaluation so it can tell, without a query
        per candidate, whether a condition is already being reported.
        """
        statement = select(Alert).where(Alert.user_id == user_id, Alert.acknowledged_at.is_(None))
        return {alert.dedupe_key: alert for alert in self.session.scalars(statement).all()}

    def find_by_key(self, user_id: int, dedupe_key: str) -> Alert | None:
        """Locate any alert (acknowledged or not) with this key.

        Needed because ``dedupe_key`` is unique per user across all alerts:
        re-raising a condition the user previously dismissed has to reuse the
        existing row rather than insert a colliding one.
        """
        statement = select(Alert).where(Alert.user_id == user_id, Alert.dedupe_key == dedupe_key)
        return self.session.scalars(statement).one_or_none()

    def count_unacknowledged(self, user_id: int) -> int:
        """Badge count for the UI - counted in SQL, not by loading the rows."""
        statement = (
            select(func.count())
            .select_from(Alert)
            .where(Alert.user_id == user_id, Alert.acknowledged_at.is_(None))
        )
        return self.session.scalar(statement) or 0
