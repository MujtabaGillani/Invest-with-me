# Architecture

This document records the decisions a reviewer would otherwise have to
reverse-engineer from the code: what was chosen, what it was chosen *over*, and
what would have to change to revisit it.

Structural facts that are obvious from the tree (there is a `services/` layer,
models live in `models/`) are not repeated here. Only the judgement calls are.

---

## 1. The product constraint: no recommendations

**Decision.** No part of this system returns a rating, a price target, a
composite score, or a buy/sell signal. Ever.

**Why.** The source guide opens by stating that no model can reliably predict
short-term price moves, and closes by noting that professional fund managers
mostly fail to beat the market. A tool built from that guide which then emitted
"BUY: 8.4/10" would contradict its own premise, and would encourage exactly the
behaviour the guide's section 7 lists as a mistake — treating one indicator as a
verdict.

**How it is enforced, not just intended.**

- The vocabulary makes it hard to violate. `MetricVerdict` is
  `STRONG / ADEQUATE / WEAK / INSUFFICIENT_DATA` — a judgement about a *number*,
  never an action. Technical readings are descriptive states (`UPTREND`,
  `OVERBOUGHT`), never instructions. This is stated at the top of
  [`core/enums.py`](../backend/app/core/enums.py) so the next person to add a
  member sees the rule first.
- `FundamentalsScore` reports **counts** (`strong: 4, weak: 1, …`) rather than a
  weighted composite. A single 0-100 grade would be the easiest thing in the
  world to add and the most damaging: it hides which criterion failed and invites
  ranking companies by it.
- `tests/api/test_meta.py::test_no_endpoint_offers_a_recommendation` asserts that
  no path in the OpenAPI schema contains `recommend`, `signal`, `rating`,
  `prediction` or `forecast`. `tests/unit/test_technicals.py::test_report_never_recommends_an_action`
  does the same for indicator commentary.

**To revisit this** you would have to delete those two tests. That is deliberate:
it makes the constraint a decision someone has to consciously reverse.

---

## 2. "Insufficient data" is a first-class outcome

**Decision.** When the figures cannot support a judgement, the metric returns
`INSUFFICIENT_DATA` with an explanation. It is never silently scored as `WEAK`,
and the calculation never raises.

**Why.** This is the difference between a tool that informs and one that misleads.
Three concrete cases:

| Situation | Naive behaviour | What this does |
| --- | --- | --- |
| Loss-making company | P/E of `-8x`, which sorts as "cheapest" | No P/E, with the reason stated |
| Two years of history | A "trend" from one comparison | No verdict; the guide asks for 3+ years |
| Company pays no dividend | Marked down as weak | Not judged — reinvesting is a legitimate strategy |

**Consequence.** Every assessor in
[`analysis/fundamentals.py`](../backend/app/analysis/fundamentals.py) is total: it
accepts `None`, zero and negative inputs and always returns an assessment. The
helpers in [`core/numeric.py`](../backend/app/core/numeric.py) return `None`
rather than raising, so callers can report the gap honestly instead of guarding
every division.

---

## 3. Thresholds are quarantined in one module

**Decision.** Every number that turns the guide's qualitative advice into a
machine check lives in [`analysis/rules.py`](../backend/app/analysis/rules.py),
each with a comment explaining the reasoning. No magic numbers in the
calculations.

**Why.** The guide says "consistent growth over several years" and "lower is
generally safer". Software needs `12.0` and `0.5`. Those numbers are **stated
judgement calls, not facts about markets**, and the honest way to ship them is to
put them where they can be argued with. Scattered through the calculations they
would be indistinguishable from typos six months later.

**Consequence.** Tuning a criterion is a one-line change plus a docstring update,
with no data backfill — because nothing derived is ever persisted (see §5).

---

## 4. The analysis layer is pure, but it returns Pydantic models

**Decision.** `app/analysis/` imports no SQLAlchemy and no FastAPI. It takes plain
dataclasses of `float` and returns Pydantic models from
[`schemas/analysis.py`](../backend/app/schemas/analysis.py) — which double as the
HTTP response contract.

**Considered and rejected:** a separate set of hand-written domain result types
with `to_schema()` translation. That is the more orthodox layering, and it was
rejected because the analysis layer's output *is* a report — there is no
behaviour to protect, only data to describe. A second parallel definition would
add a translation step, roughly 400 lines of near-duplicate field declarations,
and a place for the two copies to drift, in exchange for isolation from a
data-validation library that imposes no runtime coupling.

**The line that is actually held:** the analysis layer is kept away from
**SQLAlchemy**, not from Pydantic. An ORM row carries a session, lazy loading and
a transaction; a Pydantic model carries none of those. That is why
[`analysis/inputs.py`](../backend/app/analysis/inputs.py) exists — ORM rows are
converted to plain value objects at exactly one boundary, in
[`services/analysis.py`](../backend/app/services/analysis.py).

**How you can tell it worked:** `tests/unit/` has 100 tests over the entire rule
set, with no database, no fixtures and no HTTP client. They read like arithmetic.

---

## 5. Nothing derived is stored

**Decision.** P/E, net margin, free cash flow, debt-to-equity and every verdict
are computed on read. The database holds only figures as reported by the company.

**Why.** A cached ratio goes stale the moment either input changes, and there is
no cheap way to know when that happened — a restated filing and a price tick both
invalidate P/E. Storing raw inputs also means the numbers on screen always match
the annual report the user is reading alongside them, which matters because
guide section 8 tells them to go and check.

**Cost accepted.** Ratios are recomputed per request. For a retail-scale dataset
that is microseconds; the peer-median queries that dominate are already batched
into single statements (`latest_financials_by_company`,
`latest_price_by_company`).

**Related:** EPS is stored *as reported* rather than recomputed from
`net_profit / shares_outstanding`. The reported figure is weighted over the year
and adjusted for bonus issues, so recomputing it would disagree with the filing.

---

## 6. No holdings table — positions replay from the trade ledger

**Decision.** `trades` is an append-only ledger.
[`PortfolioService.replay`](../backend/app/services/portfolio.py) rebuilds every
position from it on each read. There is no `holdings` table.

**Considered and rejected:** a maintained `holdings` row per position. It
duplicates information the trades already fully determine, and every duplicate is
a chance to disagree with the ledger — after a partially failed request, a manual
correction, or a back-dated trade. The reconciliation code that would be needed
is larger and subtler than the replay.

**Cost accepted.** O(trades per user) per read — tens of rows for a retail
portfolio. If a portfolio ever grew large enough to matter, the fix is a cached
projection rebuilt *from this same ledger*, not a second source of truth.

**Detail that matters:** replay orders by `executed_at, id`. The `id` tie-break is
load-bearing — two trades with the same timestamp (a bulk import, a same-day buy
and sell) must replay in a stable order, or average cost would change between two
identical requests. `tests/api/test_portfolio.py::test_back_dated_trades_replay_in_execution_order_not_entry_order`
pins this.

**Cost basis is weighted average**, not FIFO, because that is what a PSX broker
statement shows — so the user can reconcile the two without arithmetic.

---

## 7. `provider.is_synthetic` is load-bearing

**Decision.** Every market data provider must declare whether its figures are
generated. The flag propagates through `/meta` and the portfolio response, and the
UI is required to label the data when it is `true`.

**Why.** The bundled dataset uses **real PSX ticker symbols with invented
financials**. That combination is genuinely useful for development and genuinely
dangerous if mislabelled — a screenshot of "OGDC: 8.2x P/E" from this app could
be mistaken for a real figure. A provider that lies about this flag is the single
worst bug this codebase could ship, which is why it is part of the
`MarketDataProvider` protocol rather than a configuration detail.

Reinforced by: a warning logged at startup and again during seeding; the flag in
the API description; `verification_sources` pointing at PUCARS, Sarmaaya and
SCSTrade so the user can check the real numbers (guide section 8); and a header
comment in the data file itself.

**Registry fails loud.** An unrecognised provider name raises at startup rather
than falling back to `seeded` — a silent fallback to synthetic data is the most
dangerous possible default here.

---

## 8. Single-user v1, with the seam already cut

**Decision.** No authentication. `deps.py::get_current_user` resolves one account
from configuration for every request.

**Why this is a scope decision and not an oversight.** The schema is already
multi-user: every user-owned table carries `user_id`, and every per-user query is
scoped by it *in the query* rather than fetched-then-checked — a scoped query
cannot leak another user's row through a forgotten `if`. Adding real
authentication is a change to one function.

**What is genuinely absent:** authorisation, sessions, rate limiting, and any
notion of trust. This is safe only for a service running locally for one person.
Deploying it as-is would expose one shared portfolio to anyone who can reach the
port.

---

## 9. Errors: one envelope, stable codes

**Decision.** Every failure — domain rule, request validation, unmatched route,
unhandled bug — returns
`{"error": {"code", "message", "details", "request_id"}}`.

**Why.** The frontend writes error handling once and branches on `error.code`
rather than parsing prose. Services raise domain exceptions from
[`core/errors.py`](../backend/app/core/errors.py) and know nothing about HTTP;
handlers in `main.py` do the translation.

**Deliberate distinctions the client can act on:**

- `company_not_found` (404) vs `insufficient_data` (422) — "no such company" and
  "not enough data for this company" need different UI.
- `validation_error` (422, a business rule: selling more than you hold) vs
  `request_validation_error` (422, a malformed payload).

**500s leak nothing.** The exception and stack trace are logged with the
correlation id; the client gets a generic message plus that id.
`tests/api/test_errors.py` asserts the internals do not appear in the response.

---

## 10. Alerts are the user's own rules firing

**Decision.** Every alert corresponds to a threshold the *user* wrote down — a
profit target, a stop-loss, a concentration limit, a review interval. None is a
prediction. The message wording is held to that, and each alert's `context`
carries the numbers so the UI can be precise without the backend pre-formatting
prose.

**Three properties that make the feature usable rather than noise:**

- **Idempotent.** Each condition produces a stable `dedupe_key` of
  `kind:subject` — never containing a price or percentage, or a tick would mint a
  new alert. Re-evaluating refreshes the existing row.
- **Self-clearing.** A condition that no longer holds is acknowledged
  automatically. Alerts that linger after the fact train the user to ignore them.
- **Fail-soft.** One company with missing filings must not abort the sweep, hence
  `AnalysisService.try_fundamentals`.

**Evaluation is an explicit `POST /alerts/evaluate`**, not a side effect of
listing. A GET must not write, and the client gets "2 new, 1 resolved" instead of
a silently changed list.

Only *holdings* are checked for fundamental red flags, and only the serious ones
(`falling_knife`, `negative_equity`, `debt_up_profit_down`). Alerting on every
flag on every company would bury the two that mean "your thesis may have broken".

---

## 11. Trade plans: one hard invariant

**Decision.** A plan cannot leave `DRAFT` until all five pre-buy questions are
answered **yes** and both a profit target and a stop-loss are set. Once
committed, it cannot be edited.

**Why.** This is the guide's central instruction — decide the exit before buying,
"not while emotionally watching the price move" — and it is the one place the
software is allowed to refuse. Everything else informs.

**Design details that follow from it:**

- Checklist answers are `bool | None`. `NULL` means *unanswered*; `False` means
  *answered honestly, and the answer is no*. Collapsing them would make an
  unfinished checklist look like a failed one, and the blocking reasons say which
  it is.
- **Blocking** reasons are the invariant. **Advisory** notes (a thin thesis, a
  target smaller than the stop) inform without refusing — those are the user's
  call, and the app does not overrule them.
- Editing a committed plan is a 409. It is a record of a decision that was acted
  on; editing it would rewrite the history the review journal exists to preserve.
- Reviews are an append-only journal, not a `last_reviewed_note` column. The value
  is in the sequence: three consecutive reviews all saying "margins still
  slipping" is how a user notices they have been rationalising rather than
  reassessing.

---

## 12. Persistence details worth knowing

**Money is `Decimal` end to end.** Never float where a value is persisted or
summed. Floats appear only inside the analysis engines, where every value is a
ratio that gets rounded for display. The conversion happens at exactly one
boundary (`analysis/inputs.py`).

**All timestamps are timezone-aware UTC**, via `core/clock.py::utcnow` and the
`UtcDateTime` column type. SQLite has no timestamp type and returns *naive*
datetimes while Postgres returns aware ones — without the decorator, the same
comparison works in production and raises `TypeError` on a developer's machine,
or the reverse. One `TypeDecorator` removes the whole class of bug.

**Enums are VARCHAR, not native Postgres `ENUM`.** Adding a sector would
otherwise need an `ALTER TYPE` migration and a deploy-ordering dance. Values are
stored as the lower-case member value, so the stored data matches the JSON API and
is readable in a `psql` session.

**A constraint naming convention is set on the metadata.** Without it, SQLite and
Postgres invent different names for the same index and Alembic autogenerate
produces noisy, non-reversible migrations.

**Migrations do not import application code.** `env.py` has a `render_item` hook
that renders `UtcDateTime` as `sa.DateTime(timezone=True)`. Autogenerate would
otherwise emit `app.db.base.UtcDateTime()` into the migration, so a historical
migration would break the day that class is renamed. `render_as_batch` is on
because SQLite cannot `ALTER COLUMN`.

**`create_all` is development-only.** Alembic owns the schema; the startup path
refuses to run either in production and logs an error telling the operator to run
`alembic upgrade head` instead.

---

## 13. Transactions

Repositories never commit. Services own the unit of work: a state-changing method
commits, a read method does not. The `get_session` dependency opens and closes a
session and rolls back on an unhandled exception, but does not commit — so the
commit boundary is visible in the code that owns the invariant, and a multi-step
operation (record a trade, recompute the holding, mark the plan executed) is
atomic.

---

## 14. Testing strategy

- `tests/unit/` — the entire rule set, no database, no HTTP. Fast, and the tests
  read as arithmetic.
- `tests/api/` — everything else through the HTTP layer, so the wiring,
  serialisation and error translation are all exercised.

**Isolation:** one in-memory SQLite database per test, created and dropped around
each test function. A savepoint-per-test scheme would be faster but would swallow
the deliberate commits in the service layer and stop the tests from exercising the
real transaction boundaries.

**Determinism:** the provider is pinned to a fixed `as_of` date, and its price
series is anchored so the final close is exactly the configured `base_price`. That
is what lets tests assert `LUCK == 892.00` rather than a tolerance.

**Expected values are hand-computed in comments**, especially in
`test_portfolio.py`. A test that records whatever the code currently returns
passes a rounding bug through unchanged.

**The demo dataset is shaped to exercise the hard paths**, not to look tidy: a
falling knife (DGKC), a loss-maker with no meaningful P/E (TRG), a bank whose
gearing must be judged against peers (HBL), a profitable company burning cash
(UNITY), and a sector too small for a reliable median (SEARL).

---

## Known limitations

Stated plainly, so nobody has to discover them:

1. **No authentication or authorisation** (§8).
2. **Bundled data is synthetic** (§7).
3. **Prices are stored closes, not live quotes.** Nothing in the system claims
   otherwise; the portfolio reports `valued_at`.
4. **Public holidays are not modelled** in the generated series — only weekends
   are skipped. Indicators only require ascending dates, so this changes nothing
   analytically.
5. **Corporate actions are not modelled.** No split, bonus-issue or rights-issue
   handling. A real provider would supply adjusted history; the trade ledger would
   need explicit adjustment entries.
6. **Peer groups are coarse.** Twelve sectors, and a company with mixed operations
   (ENGRO-style conglomerates) sits in exactly one.
7. **The suite takes ~2 minutes.** Each API test loads 24 companies × 240 price
   bars. Tolerable now; a session-scoped seeded database would be the fix if it
   becomes annoying.
