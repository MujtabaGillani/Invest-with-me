"""The simplified buy/sell screen.

Answers two questions for someone who does not want to read a seven-metric
checklist per company:

* **What could I buy?** Every company with enough stored data is scored against the
  existing fundamentals checklist, then ranked by how many criteria it *currently
  meets*. Each row carries the reasons in plain sentences, the weak spots, and the
  checks that could not be run at all.
* **What should I sell?** Every open holding is checked against the exit rules the
  user themselves committed to before buying, plus their own concentration limits.

**The line this module holds.** It ranks and it explains; it does not forecast.
There is no predicted price, no expected return, and no ordering by anything other
than published accounts and the user's own rules. "Passes 4 of 4 checks" is a
statement about filings; "will be profitable" would be a claim about the future
that nothing in this codebase - or any codebase - can support. The distinction is
the whole reason this file is safe to add on top of a product that originally
refused to rank anything at all. See ``docs/ARCHITECTURE.md`` §18.

The suggested position size and exit levels come from the user's declared limits
and :class:`~app.analysis.rules.SuggestionRules`, never from a price target. They
are risk policy, which is knowable.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.analysis.position_sizing import assess_position_size
from app.analysis.rules import DEFAULT_SUGGESTION_RULES, SuggestionRules
from app.core.clock import utcnow
from app.core.enums import MetricVerdict
from app.core.logging import get_logger
from app.repositories.companies import CompanyRepository
from app.repositories.users import InvestorProfileRepository
from app.schemas.screener import (
    BuyCandidate,
    BuyCandidatesRead,
    SellReviewItem,
    SellReviewRead,
    SuggestedEntry,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.schemas.analysis import FundamentalsReport
    from app.schemas.portfolio import HoldingRead, PortfolioRead
    from app.services.analysis import AnalysisService
    from app.services.portfolio import PortfolioService

logger = get_logger(__name__)

_MONEY = Decimal("0.01")

#: Upper bound on how many companies one screen will assess.
#:
#: Each company costs a fundamentals report, which means a peer-median query for
#: its sector. With the real provider's 740 listings that is a slow request, and a
#: screen that takes a minute to load is a screen nobody waits for. The cap is
#: reported in the response as ``companies_scanned`` so a truncated scan is never
#: silently presented as an exhaustive one.
MAX_UNIVERSE = 400

#: Plain-language rewrites of the checklist metric keys.
#:
#: The checklist's own wording is accurate but assumes vocabulary ("compounded",
#: "gearing", "free cash flow"). These are for a reader who has said they do not
#: know anything about stocks yet, and they describe *what was observed*, never
#: what will happen.
_STRENGTH_PHRASES: dict[str, str] = {
    "revenue_growth": "Sales have been growing steadily",
    "net_margin": "Keeps a healthy share of each rupee of sales as profit",
    "eps_trend": "Profit per share has been rising",
    "pe_ratio": "Cheap relative to other companies in the same sector",
    "debt_to_equity": "Not carrying much debt",
    "dividend": "Has been paying a dividend",
    "free_cash_flow": "Generates real cash, not just paper profit",
}

_WEAKNESS_PHRASES: dict[str, str] = {
    "revenue_growth": "Sales are flat or shrinking",
    "net_margin": "Thin profit margin",
    "eps_trend": "Profit per share has been falling",
    "pe_ratio": "Expensive relative to other companies in the same sector",
    "debt_to_equity": "Carrying a lot of debt",
    "dividend": "Pays little or no dividend",
    "free_cash_flow": "Burning cash",
}

_UNKNOWN_PHRASES: dict[str, str] = {
    "revenue_growth": "sales history",
    "net_margin": "profit margin",
    "eps_trend": "profit per share",
    "pe_ratio": "valuation",
    "debt_to_equity": "debt levels",
    "dividend": "dividend history",
    "free_cash_flow": "cash flow",
}


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _standing_phrase(move_pct: Decimal | None) -> str:
    """ "It is up 12.5% on what you paid." - or an honest shrug.

    Separated out because "up" and "down" are not interchangeable with a signed
    number in prose: "It is -12.5% up" reads as a bug, and this text is shown to
    someone who has said they do not know the vocabulary yet.
    """
    if move_pct is None:
        return "There is no recent price stored for it, so its standing is unknown."
    if move_pct > 0:
        return f"It is up {_money(move_pct)}% on what you paid."
    if move_pct < 0:
        return f"It is down {_money(abs(move_pct))}% on what you paid."
    return "It is level with what you paid."


class ScreenerService:
    """Builds the buy shortlist and the sell-review list.

    A read-only service: it never writes, so it never commits. Composes the
    existing analysis and portfolio services rather than reaching into
    repositories for anything they already expose, so the checklist logic has
    exactly one implementation.
    """

    def __init__(
        self,
        session: Session,
        analysis: AnalysisService,
        portfolio: PortfolioService,
        *,
        rules: SuggestionRules = DEFAULT_SUGGESTION_RULES,
        price_delay_minutes: int | None = None,
        data_is_synthetic: bool = False,
    ) -> None:
        self.session = session
        self.analysis = analysis
        self.portfolio = portfolio
        self.rules = rules
        self.companies = CompanyRepository(session)
        self.profiles = InvestorProfileRepository(session)
        self._price_delay_minutes = price_delay_minutes
        self._data_is_synthetic = data_is_synthetic

    # -- Buy side ---------------------------------------------------------

    def buy_candidates(self, user_id: int, *, limit: int = 10) -> BuyCandidatesRead:
        """Companies ranked by how many checklist criteria they currently meet."""
        universe, total = self.companies.search(limit=MAX_UNIVERSE, offset=0)
        if total > MAX_UNIVERSE:
            logger.info(
                "Screener scanned %d of %d companies (MAX_UNIVERSE cap).", MAX_UNIVERSE, total
            )

        reports = self.analysis.bulk_fundamentals([company.symbol for company in universe])
        owned = {holding.symbol for holding in self._holdings(user_id)}

        scored: list[tuple[tuple[int, int, int, int, str], BuyCandidate]] = []
        for symbol, report in reports.items():
            candidate = self._to_candidate(report, already_owned=symbol in owned)
            if candidate.checks_passed < self.rules.min_strong_checks:
                continue
            # Most criteria met first; then adequate; then fewest weak; then
            # fewest unknown, so a company we can actually see beats one we
            # cannot. Symbol last, purely so the order is deterministic.
            sort_key = (
                -candidate.checks_passed,
                -candidate.checks_adequate,
                candidate.checks_weak,
                candidate.checks_unknown,
                candidate.symbol,
            )
            scored.append((sort_key, candidate))

        scored.sort(key=lambda pair: pair[0])

        # Timing context and sizing are computed only for the rows actually
        # returned - both cost extra queries per company. Read schemas are frozen,
        # so this rebuilds rather than mutates.
        profile_inputs = self._sizing_inputs(user_id)
        top = [
            candidate.model_copy(
                update={
                    "timing_note": self._timing_note(candidate.symbol),
                    "suggested": self._suggest_entry(candidate, *profile_inputs),
                }
            )
            for _key, candidate in scored[:limit]
        ]

        return BuyCandidatesRead(
            candidates=top,
            companies_scanned=len(universe),
            companies_skipped=len(universe) - len(reports),
            as_of=utcnow(),
            price_delay_minutes=self._price_delay_minutes,
            data_is_synthetic=self._data_is_synthetic,
            unavailable_checks=self._unavailable_checks(reports),
        )

    def _to_candidate(self, report: FundamentalsReport, *, already_owned: bool) -> BuyCandidate:
        """Turn a full checklist report into one plain-language row."""
        why: list[str] = []
        watch: list[str] = []
        unknown_labels: list[str] = []

        for metric in report.metrics:
            if metric.verdict is MetricVerdict.STRONG:
                phrase = _STRENGTH_PHRASES.get(metric.key)
                if phrase:
                    why.append(phrase)
            elif metric.verdict is MetricVerdict.WEAK:
                phrase = _WEAKNESS_PHRASES.get(metric.key)
                if phrase:
                    watch.append(phrase)
            elif metric.verdict is MetricVerdict.INSUFFICIENT_DATA:
                label = _UNKNOWN_PHRASES.get(metric.key)
                if label:
                    unknown_labels.append(label)

        if unknown_labels:
            # Named explicitly rather than left as a count. "3 checks unavailable"
            # invites the reader to assume the missing ones were fine.
            watch.append("No published data for: " + ", ".join(sorted(unknown_labels)) + ".")

        score = report.score
        return BuyCandidate(
            symbol=report.symbol,
            company_name=report.company_name,
            sector=report.sector,
            sector_label=report.sector_label,
            checks_passed=score.strong,
            checks_adequate=score.adequate,
            checks_weak=score.weak,
            checks_unknown=score.insufficient_data,
            checks_total=score.metrics_assessed,
            last_price=report.reference_price,
            last_price_date=report.reference_price_date,
            why=why,
            watch_out_for=watch,
            already_owned=already_owned,
        )

    def _unavailable_checks(self, reports: dict[str, FundamentalsReport]) -> list[str]:
        """Checks that no company could satisfy, because the source lacks the data.

        Distinguishes "this company has thin filings" from "the active data source
        does not publish this at all" - the second is a property of the provider and
        belongs at the top of the screen, not repeated on every row.
        """
        if not reports:
            return []
        always_unknown: set[str] | None = None
        for report in reports.values():
            unknown = {
                metric.key
                for metric in report.metrics
                if metric.verdict is MetricVerdict.INSUFFICIENT_DATA
            }
            always_unknown = unknown if always_unknown is None else (always_unknown & unknown)
        return sorted(_UNKNOWN_PHRASES.get(key, key) for key in (always_unknown or set()))

    def _timing_note(self, symbol: str) -> str | None:
        """Where the price sits in its own recent range, in plain words.

        Explicitly *context*, not a signal. The guide's position - and this app's -
        is that no indicator predicts a short-term move, so this says where the
        price has been, and stops there.
        """
        try:
            report = self.analysis.technicals(symbol)
        except Exception:
            logger.debug("No technicals available for %s; skipping timing note.", symbol)
            return None

        trend = str(report.trend_direction or "unknown")
        position = str(report.moving_average_position or "unknown")
        zone = str(report.rsi_zone or "unknown")

        # Full clauses rather than glued-together enum names: "Price has been
        # downtrend recently" is not a sentence, and this text is the whole point of
        # the screen for someone who does not know the vocabulary.
        opening = {
            "uptrend": "The price has been rising over recent months",
            "downtrend": "The price has been falling over recent months",
            "sideways": "The price has been flat over recent months",
        }.get(trend)
        if opening is None:
            return None

        # Trend and moving-average position genuinely can disagree - a pullback
        # inside a longer uptrend is exactly that - so the two clauses are joined
        # with "though" when they point opposite ways and "and" when they agree.
        average_clause = {
            "above_both": "above both its 50- and 200-day averages",
            "below_both": "below both its 50- and 200-day averages",
        }.get(position)
        sentence = opening
        if average_clause is not None:
            agrees = (trend == "uptrend" and position == "above_both") or (
                trend == "downtrend" and position == "below_both"
            )
            joiner = ", and it is still " if agrees else ", though it is still "
            sentence += joiner + average_clause

        tail = {
            "overbought": " It has climbed quickly, so this is not a calm moment to buy.",
            "oversold": (
                " It has dropped quickly, which can mean a bargain or a company in trouble - "
                "the checks above are the way to tell which."
            ),
        }.get(zone, "")
        return sentence + "." + tail

    def _sizing_inputs(self, user_id: int) -> tuple[Decimal, Decimal, Decimal]:
        """``(portfolio_value, investable_capital, max_position_pct)``.

        Falls back to zero capital and the profile default when no profile exists
        yet, which yields a null suggested amount rather than a made-up one.
        """
        profile = self.profiles.get_for_user(user_id)
        portfolio_value = self.portfolio.portfolio_value(user_id)
        if profile is None:
            return portfolio_value, Decimal(0), Decimal("15")
        return portfolio_value, profile.investable_capital, profile.max_position_pct

    def _suggest_entry(
        self,
        candidate: BuyCandidate,
        portfolio_value: Decimal,
        investable_capital: Decimal,
        max_position_pct: Decimal,
    ) -> SuggestedEntry:
        """Position size and exit levels, from the user's limits and the rules."""
        sizing = assess_position_size(
            intended_amount=None,
            portfolio_value=portfolio_value,
            investable_capital=investable_capital,
            max_position_pct=max_position_pct,
        )
        amount = sizing.suggested_max_amount if sizing.suggested_max_amount > 0 else None

        price = candidate.last_price
        shares: int | None = None
        target_price: Decimal | None = None
        stop_price: Decimal | None = None
        if price is not None and price > 0:
            if amount is not None:
                shares = int((amount / price).to_integral_value(rounding=ROUND_DOWN))
            target_price = _money(price * (Decimal(100) + self.rules.profit_target_pct) / 100)
            stop_price = _money(price * (Decimal(100) - self.rules.stop_loss_pct) / 100)

        return SuggestedEntry(
            suggested_amount=amount,
            suggested_shares=shares,
            profit_target_pct=self.rules.profit_target_pct,
            profit_target_price=target_price,
            stop_loss_pct=self.rules.stop_loss_pct,
            stop_loss_price=stop_price,
            basis=(
                f"Amount is your own {max_position_pct}% single-position limit. The "
                f"target and stop are starting points for you to confirm, not forecasts "
                f"- they set what you would accept as enough gain and as too much loss."
            ),
        )

    # -- Sell side --------------------------------------------------------

    def sell_review(self, user_id: int) -> SellReviewRead:
        """Holdings that have crossed one of the user's own rules."""
        portfolio = self._portfolio(user_id)
        items: list[SellReviewItem] = []
        for holding in portfolio.holdings:
            items.extend(self._review_items(holding))
        items.extend(self._concentration_items(portfolio))

        # Crossed exit rules first; within a group, the largest move first, so the
        # most consequential decision is at the top.
        items.sort(
            key=lambda item: (
                0 if item.urgency == "act_now" else 1,
                -abs(item.unrealised_pl_pct or Decimal(0)),
                item.symbol,
            )
        )
        return SellReviewRead(
            items=items,
            holdings_count=len(portfolio.holdings),
            as_of=utcnow(),
            price_delay_minutes=self._price_delay_minutes,
            data_is_synthetic=self._data_is_synthetic,
        )

    def _review_items(self, holding: HoldingRead) -> list[SellReviewItem]:
        """Every rule this one holding has crossed."""
        items: list[SellReviewItem] = []
        price = holding.last_price
        move = holding.unrealised_pl_pct

        target = holding.profit_target_price
        if price is not None and target is not None and price >= target:
            items.append(
                self._item(
                    holding,
                    reason="profit_target_reached",
                    urgency="act_now",
                    headline=(
                        f"{holding.symbol} has reached the profit target you set. "
                        f"It is at PKR {_money(price)}, and your target was PKR {_money(target)}."
                    ),
                    what_you_said="Take the profit when it gets here.",
                )
            )

        stop = holding.stop_loss_price
        if price is not None and stop is not None and price <= stop:
            items.append(
                self._item(
                    holding,
                    reason="stop_loss_breached",
                    urgency="act_now",
                    headline=(
                        f"{holding.symbol} has fallen through the stop-loss you set. "
                        f"It is at PKR {_money(price)}, and your stop was PKR {_money(stop)}."
                    ),
                    what_you_said="Cut the loss if it falls this far.",
                )
            )

        if holding.missing_exit_rules:
            # Not a sell signal - the opposite. It says the decision has no rule
            # behind it yet, which is the moment to write one down rather than
            # improvise later while the price is moving.
            items.append(
                self._item(
                    holding,
                    reason="no_exit_rules",
                    urgency="decide_soon",
                    headline=(
                        f"You have not decided when you would sell {holding.symbol}. "
                        + _standing_phrase(move)
                    ),
                    what_you_said=None,
                )
            )

        return items

    def _concentration_items(self, portfolio: PortfolioRead) -> list[SellReviewItem]:
        """The user's own diversification limits, where they are exceeded.

        A reason to trim rather than to exit, so it never gets ``act_now``.
        """
        by_symbol = {holding.symbol: holding for holding in portfolio.holdings}
        items: list[SellReviewItem] = []
        for warning in portfolio.concentration_warnings:
            holding = by_symbol.get(warning.subject)
            if holding is None:
                # A sector-level warning has no single holding behind it; the
                # portfolio screen presents those in full.
                continue
            items.append(
                self._item(
                    holding,
                    reason="position_too_large",
                    urgency="decide_soon",
                    headline=warning.message,
                    what_you_said=(
                        f"Keep any single holding under {warning.limit_pct}% of the portfolio."
                    ),
                )
            )
        return items

    @staticmethod
    def _item(
        holding: HoldingRead,
        *,
        reason: str,
        urgency: str,
        headline: str,
        what_you_said: str | None,
    ) -> SellReviewItem:
        return SellReviewItem(
            symbol=holding.symbol,
            company_name=holding.company_name,
            sector_label=holding.sector_label,
            quantity=holding.quantity,
            average_cost=holding.average_cost,
            last_price=holding.last_price,
            unrealised_pl=holding.unrealised_pl,
            unrealised_pl_pct=holding.unrealised_pl_pct,
            reason=reason,
            urgency=urgency,
            headline=headline,
            what_you_said=what_you_said,
            profit_target_price=holding.profit_target_price,
            stop_loss_price=holding.stop_loss_price,
            last_reviewed_at=holding.last_reviewed_at,
        )

    # -- Shared -----------------------------------------------------------

    def _portfolio(self, user_id: int) -> PortfolioRead:
        return self.portfolio.get_portfolio(
            user_id, market_data_is_synthetic=self._data_is_synthetic
        )

    def _holdings(self, user_id: int) -> list[HoldingRead]:
        return list(self._portfolio(user_id).holdings)
