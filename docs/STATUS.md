# Status and resume notes

Last updated: 2026-08-19 (session 5).

## Verified working right now

**Backend** (from `backend/`):

```bash
.venv/Scripts/python.exe -m pytest -q                              # 435 passed
.venv/Scripts/python.exe -m ruff check app tests scripts alembic   # clean
.venv/Scripts/python.exe -m ruff format --check ...                # clean
.venv/Scripts/python.exe -m mypy                                   # clean, 98 files
.venv/Scripts/alembic.exe upgrade head                             # matches models exactly
```

**Frontend** (from `frontend/`):

```bash
npm run typecheck    # clean, with strict + noUncheckedIndexedAccess + exactOptionalPropertyTypes
npm run lint         # clean, type-aware rules enabled
npm test             # 91 passed
npm run build        # 408 kB / 123 kB gzipped
```

**Both together** — verified by running the real servers and driving them over HTTP:

- Vite dev server serves the app and proxies `/api` to the backend
- Every page and feature module transforms without error (19/19 checked)
- Live data flows end to end: LUCK's fundamentals, technicals, the demo portfolio
  (3 holdings, PKR 400,720), 4 plans in 3 different states, 3 watchlist entries

## Complete

### Backend

23 endpoints across companies, analysis, profile, watchlist, plans, portfolio,
alerts and meta. Layered `api → services → repositories → models`, with a pure
`analysis/` package that imports neither SQLAlchemy nor FastAPI. Alembic owns the
schema. 344 tests at 94% coverage.

### Frontend

Nine screens, wired to the real API:

| Screen | What it does |
| --- | --- |
| Dashboard | Ordered by what needs attention — unwritten profile, open alerts, unfinished drafts, then the portfolio |
| Your plan | The profile form, with the server's derived warnings beside it |
| Companies | Search and sector filter in the URL; shows which analyses each company has data for |
| Company | Fundamentals / technicals / reported figures, tab in the URL |
| Watchlist | Research note required; entry-price distance per row |
| Trade plans | List with per-question checklist markers |
| Plan detail | Checklist, thesis, exit rules, readiness panel, review journal |
| Portfolio | Holdings, exit-rule prices, sector allocation, concentration warnings, trade ledger |
| Alerts | Explicit re-check, per-kind guidance, dismiss |

Notable pieces:

- **Types are generated from the backend's OpenAPI schema** (`npm run codegen`),
  with readable aliases in `src/types/index.ts`. FE and BE cannot drift.
- **One HTTP entry point** (`src/lib/apiClient.ts`) parses the error envelope into
  an `ApiError` carrying the server's stable `code`, so components branch on the
  failure rather than matching prose.
- **The synthetic-data banner is not dismissible** and defaults to *showing* while
  metadata loads — if the app cannot confirm the data is real it assumes it is not.
- **No charting dependency.** Two inline SVG components cover the sparkline and the
  price line; both are `aria-hidden` with the figures present as text.
- **Verdicts are never coloured as advice.** A weak metric gets a muted badge
  labelled "Weak", and `insufficient_data` renders as "Not enough data" with a
  tooltip saying it is not a bad result.

### Documentation

- `README.md` — what it does, how to run both halves, configuration, the auth and
  data-provenance caveats
- `docs/ARCHITECTURE.md` — 14 recorded decisions with the alternatives that were
  rejected, plus a stated list of known limitations

## Bugs found and fixed by writing tests

1. **Non-deterministic "newest first" ordering** (backend). `created_at` is
   database-generated and SQLite's `CURRENT_TIMESTAMP` has one-second resolution,
   so same-second rows sorted arbitrarily. Added an `id` tie-break to plan listing,
   the review journal, alerts and the watchlist.
2. **Select-then-delete-each-row on market re-sync** (backend). Now a single
   `DELETE` plus `add_all`.
3. **Abort detection relied on `instanceof DOMException`** (frontend). That is not
   reliably an `Error` subclass across runtimes, so a cancelled request could have
   been reported as a network failure. Now checked by `name`.
4. **Props-into-state sync via `useEffect`** (frontend). Flagged by
   `react-hooks/set-state-in-effect`. Replaced with re-seeding from the mutation
   response plus a `key` for navigation — which also fixed a real wart, since the
   server normalises `"25"` to `"25.00"` and the form previously stayed "dirty"
   after saving.

## Closed since session 3

- **`mypy`** now runs over `app`, `tests`, `scripts` and `alembic/env.py` (98 files)
  and is clean. Its first run found 17 findings across 3 files — all typing
  precision, no logic bugs.
- **CI** at `.github/workflows/ci.yml`: three jobs (backend, frontend, API
  contract). The contract job regenerates `openapi.json` and `api.d.ts` and fails if
  the committed copies are stale — without it the generated-types guarantee is
  unenforced, because a stale `api.d.ts` type-checks perfectly while describing an
  API that no longer exists. Both new backend gates were run locally first.
- **Docker**: multi-stage `Dockerfile` per half, `nginx.conf`, and
  `docker-compose.yml` bringing up Postgres + API + nginx. It exists to exercise the
  Postgres path, not to deploy.
- **Form component tests**: `TradeForm` (10) and `ProfileForm` (9).
- **A shipped bug, found and fixed.** `PSX_CORS_ORIGINS` is documented as
  comma-separated and the README says `cp .env.example .env` — doing exactly that
  crashed startup, because pydantic-settings JSON-decodes `list[str]` before
  validators run. Fixed with `enable_decoding=False`. `tests/unit/test_config.py`
  (21 tests) now drives settings from environment variables and from a real `.env`
  file, and asserts the shipped `.env.example` loads.
- **SQLite sidecars removed from tracking.** `.gitignore` covered `*.db` but not
  `*.db-wal` / `*.db-shm`, so a 1.7 MB write-ahead log reached the initial commit.

## Remaining work

Nothing is blocking. In rough order of value:

1. **Wire up `PsxDataProvider.fetch_quote`.** The real provider is built and
   verified (see below), but `fetch_quote` has no caller yet: the banner reads the
   delay from `/meta` metadata, not from a live quote. An endpoint returning a
   symbol's latest price with its `observed_at` stamp is the next step towards
   "is this price current enough to act on".
2. **Fill in the balance sheet and cash flow.** Three of seven fundamentals
   metrics report `insufficient_data` under the real provider because no free
   source publishes those figures. A manual-entry path for the companies you
   actually hold would restore the full checklist; a licensed feed would too.
3. **Accessibility pass.** Controls are label-bound, focus is visible and the tabs
   implement the ARIA pattern, but nothing has been checked with a screen reader
   or axe.
4. **Component tests for the pages themselves.** Both forms, `PlanReadiness`,
   `Badge`, `format` and `apiClient` are covered; the nine pages are not.
5. **Backend suite takes ~2.5 minutes** — each API test loads 24 companies × 240
   price bars. A session-scoped seeded database would cut it.
6. **Docker images are unbuilt.** The files are written and the YAML validates, but
   `docker compose up --build` has not been run here — no Docker daemon available.

## Closed in session 5

**The real PSX provider is built, verified against the live exchange, and wired
in.** `PSX_MARKET_DATA_PROVIDER=psx` now serves real data end to end.

- `app/providers/psx.py` — `PsxDataProvider`, composing `psxdata` (listings, daily
  OHLCV) with the PSX Data Portal company pages (annual Sales, Profit after
  Taxation, EPS). 66 unit tests, no network and no pandas required: `psxdata` is
  faked and the HTML fixtures are hand-written, so no PSX data is committed here.
- **Verified live**: 740 equities from 1,002 raw symbols; LUCK's 260 price bars and
  close of 439.30 on 18 Aug 2026 match the DPS page exactly; four fiscal years of
  financials parsed and correctly scaled from thousands; synced into SQLite and
  served over HTTP through all 23 endpoints.
- **`Sector` widened from 12 to 39 members** to mirror PSX's own 38 sectors.
  A pure Python change with no migration, exactly as `db/base.py::enum_column` was
  designed for. Collapsing 27 sectors into `other` would have made peer-relative
  P/E compare banks against sugar mills.
- **`price_delay_minutes` added to the provider contract** and surfaced by the
  banner, which now has a "Delayed prices" variant for real-but-lagging data
  (ARCHITECTURE §16).
- **A real bug, found on real data.** The fundamentals checklist scored Lucky
  Cement's EPS as **weak** while its profit tripled, because PSX publishes EPS
  unadjusted and the share count had quadrupled in a bonus issue. `assess_eps_trend`
  now derives the implied share count and reports `insufficient_data` when it moved
  more than 25% (ARCHITECTURE §17).
- **Dead code removed.** `knip` over the frontend and an AST scan over the backend:
  deleted `useSectorLabel`, `useIsSyntheticData`, `useUpdateWatchlistItem`,
  `TechnicalSummaryLine` and `deps.py::session_generator`; de-exported `Spinner`,
  `API_BASE_URL` and `TRADES_PAGE_SIZE`, which are only used inside their own
  modules. No unused *files* in either half. The type aliases in
  `src/types/index.ts` were deliberately kept — that is a readable facade over the
  generated `api.d.ts`, not dead weight.

## Git

Pushed to <https://github.com/MujtabaGillani/Invest-with-me> as `6cec0c9` on `main`.

Repo-local identity is `MujtabaGillani <msyed2782@gmail.com>` - set with
`git config user.name/user.email` **without** `--global`, because the machine's
global identity is a different account.

Everything listed under "Closed since session 3" is **uncommitted** on top of
`6cec0c9`. The user commits and pushes; nothing in this repo does it for them.
