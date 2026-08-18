"""The portfolio monitor (guide section 6).

Every alert this service raises is one of the user's **own pre-committed rules**
crossing its threshold - a profit target they chose, a stop-loss they set, a
concentration limit they declared, a review interval they picked. None of them is
a prediction or a recommendation, and the message wording is held to that.

Design notes:

* **Idempotent.** Re-evaluating the same portfolio does not create duplicate
  rows. Each condition produces a stable ``dedupe_key``; an existing open alert
  with that key is refreshed rather than re-inserted.
* **Self-clearing.** A condition that no longer holds - the price came back above
  the stop, the position was trimmed under the limit - is acknowledged
  automatically. Alerts that linger after the fact train the user to ignore them.
* **Fail-soft.** One company with missing data must not abort the sweep, so
  fundamentals are fetched through ``try_fundamentals``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import days_between, utcnow
from app.core.enums import AlertKind, AlertSeverity
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.alert import Alert
from app.repositories.alerts import AlertRepository
from app.repositories.plans import TradePlanRepository
from app.repositories.watchlist import WatchlistRepository
from app.schemas.alerts import AlertEvaluationResult, AlertRead
from app.schemas.portfolio import HoldingRead, PortfolioRead
from app.services.analysis import AnalysisService
from app.services.portfolio import PortfolioService
from app.services.profile import ProfileService
from app.services.watchlist import WatchlistService

logger = get_logger(__name__)

#: Red-flag keys serious enough to interrupt the user. The remaining flags are
#: informational and are left to the analysis screen - alerting on all of them
#: would bury the two that mean "your thesis may have broken".
_ALERTING_RED_FLAGS: frozenset[str] = frozenset(
    {"falling_knife", "negative_equity", "debt_up_profit_down"}
)


@dataclass(frozen=True, slots=True)
class AlertCandidate:
    """A condition the monitor has detected, before persistence."""

    kind: AlertKind
    severity: AlertSeverity
    message: str
    dedupe_key: str
    company_id: int | None = None
    context: dict[str, Any] | None = None


class AlertService:
    """Detect, persist and acknowledge alerts."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.alerts = AlertRepository(session)
        self.plans = TradePlanRepository(session)
        self.watchlist = WatchlistRepository(session)
        self.portfolio = PortfolioService(session)
        self.profiles = ProfileService(session)
        self.analysis = AnalysisService(session)

    # -- Reads -------------------------------------------------------------

    def list_alerts(self, user_id: int, *, include_acknowledged: bool = False) -> list[AlertRead]:
        """Stored alerts, newest first."""
        rows = self.alerts.list_for_user(user_id, include_acknowledged=include_acknowledged)
        return [self._to_read_model(alert) for alert in rows]

    def count_open(self, user_id: int) -> int:
        """Unacknowledged alert count, for the navigation badge."""
        return self.alerts.count_unacknowledged(user_id)

    # -- Writes ------------------------------------------------------------

    def acknowledge(self, user_id: int, alert_id: int) -> AlertRead:
        """Dismiss one alert. The row is kept as part of the journal."""
        alert = self.alerts.get_for_user(user_id, alert_id)
        if alert is None:
            raise NotFoundError("Alert not found.", details={"alert_id": alert_id})
        if alert.acknowledged_at is None:
            alert.acknowledged_at = utcnow()
            self.session.commit()
        return self._to_read_model(alert)

    def acknowledge_all(self, user_id: int) -> int:
        """Dismiss every open alert. Returns how many were dismissed."""
        now = utcnow()
        rows = self.alerts.list_for_user(user_id, include_acknowledged=False, limit=1000)
        for alert in rows:
            alert.acknowledged_at = now
        if rows:
            self.session.commit()
        return len(rows)

    def evaluate(self, user_id: int) -> AlertEvaluationResult:
        """Run every rule over the current portfolio and reconcile the alert table.

        Commits once, at the end: the whole evaluation is a single unit of work, so
        a failure halfway through leaves no partially-updated alert list.
        """
        candidates = self._detect(user_id)
        by_key = {candidate.dedupe_key: candidate for candidate in candidates}
        open_alerts = self.alerts.open_alerts_by_key(user_id)
        now = utcnow()

        created = 0
        already_open = 0
        for key, candidate in by_key.items():
            existing = open_alerts.get(key)
            if existing is not None:
                # Refresh the wording and numbers: the condition still holds but the
                # specifics (current price, current weight) have moved on.
                existing.message = candidate.message
                existing.severity = candidate.severity
                existing.context = candidate.context or {}
                already_open += 1
                continue

            previously_dismissed = self.alerts.find_by_key(user_id, key)
            if previously_dismissed is not None:
                # The user dismissed this before and it has recurred. Reopen the
                # same row - the unique constraint on (user, key) requires reuse,
                # and reopening preserves the history of when it first fired.
                previously_dismissed.acknowledged_at = None
                previously_dismissed.message = candidate.message
                previously_dismissed.severity = candidate.severity
                previously_dismissed.context = candidate.context or {}
                created += 1
                continue

            self.session.add(
                Alert(
                    user_id=user_id,
                    company_id=candidate.company_id,
                    kind=candidate.kind,
                    severity=candidate.severity,
                    message=candidate.message,
                    context=candidate.context or {},
                    dedupe_key=key,
                )
            )
            created += 1

        # Anything open that no longer has a matching candidate has resolved.
        resolved = 0
        for key, alert in open_alerts.items():
            if key not in by_key:
                alert.acknowledged_at = now
                resolved += 1

        self.session.commit()
        logger.info(
            "Alert evaluation for user %s: %s new, %s still open, %s resolved.",
            user_id,
            created,
            already_open,
            resolved,
        )
        return AlertEvaluationResult(
            created=created,
            already_open=already_open,
            resolved=resolved,
            alerts=self.list_alerts(user_id),
        )

    # -- Detection ---------------------------------------------------------

    def _detect(self, user_id: int) -> list[AlertCandidate]:
        """Run all rules and return every condition currently true."""
        candidates: list[AlertCandidate] = []
        portfolio = self.portfolio.get_portfolio(user_id)
        profile = self.profiles.get_effective(user_id)

        for holding in portfolio.holdings:
            candidates.extend(self._exit_rule_candidates(holding))
            candidates.extend(self._review_candidates(holding, profile.review_interval_days))
            candidates.extend(self._fundamental_candidates(holding))

        candidates.extend(self._concentration_candidates(portfolio))
        candidates.extend(self._watchlist_candidates(user_id))
        return candidates

    @staticmethod
    def build_dedupe_key(kind: AlertKind, subject: str) -> str:
        """Stable identity for a condition: ``kind:subject``.

        ``subject`` is a symbol, a sector value, or a watchlist id - never a price
        or a percentage. Including a moving number would mint a new alert every
        time the price ticked, which is exactly what de-duplication exists to
        prevent.
        """
        return f"{kind.value}:{subject}"

    def _exit_rule_candidates(self, holding: HoldingRead) -> list[AlertCandidate]:
        """Profit target reached, or stop-loss breached.

        Both are evaluated against the *latest stored close*, so the message says
        what the price has done - not what the user should do about it.
        """
        candidates: list[AlertCandidate] = []
        price = holding.last_price
        if price is None:
            return candidates

        if holding.profit_target_price is not None and price >= holding.profit_target_price:
            candidates.append(
                AlertCandidate(
                    kind=AlertKind.PROFIT_TARGET_REACHED,
                    severity=AlertSeverity.INFO,
                    company_id=holding.company_id,
                    dedupe_key=self.build_dedupe_key(
                        AlertKind.PROFIT_TARGET_REACHED, holding.symbol
                    ),
                    message=(
                        f"{holding.symbol} has reached the profit target you set before buying. "
                        f"At PKR {price:,} it is "
                        f"{holding.unrealised_pl_pct or Decimal(0):g}% above your average cost "
                        f"of PKR {holding.average_cost:,}. You planned to take something off the "
                        "table at this level."
                    ),
                    context={
                        "symbol": holding.symbol,
                        "last_price": str(price),
                        "target_price": str(holding.profit_target_price),
                        "average_cost": str(holding.average_cost),
                        "unrealised_pl_pct": str(holding.unrealised_pl_pct or ""),
                    },
                )
            )

        if holding.stop_loss_price is not None and price <= holding.stop_loss_price:
            candidates.append(
                AlertCandidate(
                    kind=AlertKind.STOP_LOSS_BREACHED,
                    severity=AlertSeverity.CRITICAL,
                    company_id=holding.company_id,
                    dedupe_key=self.build_dedupe_key(AlertKind.STOP_LOSS_BREACHED, holding.symbol),
                    message=(
                        f"{holding.symbol} has fallen through the stop-loss you set before "
                        f"buying. At PKR {price:,} it is at or below your stop level of "
                        f"PKR {holding.stop_loss_price:,}. This is the rule you wrote down to "
                        "stop a small loss becoming a large one."
                    ),
                    context={
                        "symbol": holding.symbol,
                        "last_price": str(price),
                        "stop_price": str(holding.stop_loss_price),
                        "average_cost": str(holding.average_cost),
                        "unrealised_pl_pct": str(holding.unrealised_pl_pct or ""),
                    },
                )
            )

        return candidates

    def _review_candidates(
        self, holding: HoldingRead, review_interval_days: int
    ) -> list[AlertCandidate]:
        """Thesis check-in overdue, or no exit rules recorded at all."""
        candidates: list[AlertCandidate] = []

        if holding.missing_exit_rules:
            candidates.append(
                AlertCandidate(
                    kind=AlertKind.THESIS_REVIEW_DUE,
                    severity=AlertSeverity.WARNING,
                    company_id=holding.company_id,
                    dedupe_key=self.build_dedupe_key(
                        AlertKind.THESIS_REVIEW_DUE, f"{holding.symbol}:no-plan"
                    ),
                    message=(
                        f"You hold {holding.symbol} with no profit target or stop-loss written "
                        "down. Deciding those now, while you are not watching the price move, is "
                        "the whole point of setting them in advance."
                    ),
                    context={"symbol": holding.symbol, "reason": "no_exit_rules"},
                )
            )
            return candidates

        if holding.last_reviewed_at is None:
            return candidates

        days_since = days_between(holding.last_reviewed_at, utcnow())
        if days_since >= review_interval_days:
            candidates.append(
                AlertCandidate(
                    kind=AlertKind.THESIS_REVIEW_DUE,
                    severity=AlertSeverity.INFO,
                    company_id=holding.company_id,
                    dedupe_key=self.build_dedupe_key(AlertKind.THESIS_REVIEW_DUE, holding.symbol),
                    message=(
                        f"It has been {days_since} days since you last checked your reason for "
                        f"owning {holding.symbol}, against a review interval of "
                        f"{review_interval_days} days. Does the original thesis still hold?"
                    ),
                    context={
                        "symbol": holding.symbol,
                        "days_since_review": days_since,
                        "review_interval_days": review_interval_days,
                    },
                )
            )
        return candidates

    def _fundamental_candidates(self, holding: HoldingRead) -> list[AlertCandidate]:
        """Serious red flags in a company the user actually owns.

        Only holdings are checked, not the whole market: an alert about a company
        the user has no money in is noise, and the analysis screen already reports
        every flag on demand.
        """
        report = self.analysis.try_fundamentals(holding.symbol)
        if report is None:
            return []

        serious = [flag for flag in report.red_flags if flag.key in _ALERTING_RED_FLAGS]
        if not serious:
            return []

        flag = serious[0]
        return [
            AlertCandidate(
                kind=AlertKind.FUNDAMENTAL_RED_FLAG,
                severity=(
                    AlertSeverity.CRITICAL if flag.severity == "critical" else AlertSeverity.WARNING
                ),
                company_id=holding.company_id,
                # Keyed on the flag, so a *different* flag appearing later raises
                # its own alert instead of silently overwriting this one.
                dedupe_key=self.build_dedupe_key(
                    AlertKind.FUNDAMENTAL_RED_FLAG, f"{holding.symbol}:{flag.key}"
                ),
                message=(
                    f"{holding.symbol}: {flag.title}. {flag.detail} This is the kind of change "
                    "that matters more than a price move - check whether your reason for owning "
                    "it still holds."
                ),
                context={
                    "symbol": holding.symbol,
                    "flag": flag.key,
                    "title": flag.title,
                    "other_flags": [item.key for item in serious[1:]],
                },
            )
        ]

    def _concentration_candidates(self, portfolio: PortfolioRead) -> list[AlertCandidate]:
        """Position and sector limits the user set for themselves.

        Reuses the warnings the portfolio service already computed rather than
        recalculating the weights - two implementations of the same limit would
        eventually disagree, and the user would see a warning on one screen and not
        the other.
        """
        candidates: list[AlertCandidate] = []
        for warning in portfolio.concentration_warnings:
            kind = (
                AlertKind.POSITION_CONCENTRATION
                if warning.kind == "position"
                else AlertKind.SECTOR_CONCENTRATION
            )
            candidates.append(
                AlertCandidate(
                    kind=kind,
                    severity=AlertSeverity.WARNING,
                    company_id=None,
                    dedupe_key=self.build_dedupe_key(kind, warning.subject),
                    message=warning.message,
                    context={
                        "subject": warning.subject,
                        "weight_pct": str(warning.weight_pct),
                        "limit_pct": str(warning.limit_pct),
                    },
                )
            )
        return candidates

    def _watchlist_candidates(self, user_id: int) -> list[AlertCandidate]:
        """A watched company has reached the entry price the user named."""
        candidates: list[AlertCandidate] = []
        for item in WatchlistService(self.session).list_items(user_id):
            if not item.entry_price_reached or item.last_close is None:
                continue
            candidates.append(
                AlertCandidate(
                    kind=AlertKind.WATCHLIST_ENTRY_PRICE_REACHED,
                    severity=AlertSeverity.INFO,
                    company_id=item.company_id,
                    dedupe_key=self.build_dedupe_key(
                        AlertKind.WATCHLIST_ENTRY_PRICE_REACHED, item.symbol
                    ),
                    message=(
                        f"{item.symbol} is at PKR {item.last_close:,}, at or below the "
                        f"PKR {item.target_entry_price:,} entry price you noted. Work through the "
                        "pre-buy checklist before acting - a price level on its own is not a "
                        "reason to buy."
                    ),
                    context={
                        "symbol": item.symbol,
                        "last_close": str(item.last_close),
                        "target_entry_price": str(item.target_entry_price),
                    },
                )
            )
        return candidates

    # -- Internals ---------------------------------------------------------

    @staticmethod
    def _to_read_model(alert: Alert) -> AlertRead:
        return AlertRead(
            id=alert.id,
            kind=alert.kind,
            severity=alert.severity,
            message=alert.message,
            context=alert.context or {},
            company_id=alert.company_id,
            symbol=alert.company.symbol if alert.company else None,
            company_name=alert.company.name if alert.company else None,
            created_at=alert.created_at,
            acknowledged_at=alert.acknowledged_at,
            is_acknowledged=alert.is_acknowledged,
        )
