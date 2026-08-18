# Status and resume notes

Last updated: 2026-08-18 (session 3).

## Verified working right now

**Backend** (from `backend/`):

```bash
.venv/Scripts/python.exe -m pytest tests/ -q                       # 344 passed
.venv/Scripts/python.exe -m pytest tests/ -q --cov                 # 94% coverage
.venv/Scripts/python.exe -m ruff check app tests alembic scripts   # clean
.venv/Scripts/alembic.exe upgrade head                             # matches models exactly
```

**Frontend** (from `frontend/`):

```bash
npm run typecheck    # clean, with strict + noUncheckedIndexedAccess + exactOptionalPropertyTypes
npm run lint         # clean, type-aware rules enabled
npm test             # 64 passed
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

## Remaining work

Nothing is blocking. In rough order of value:

1. **Component tests for the remaining screens.** `format`, `apiClient`, `Badge`
   and `PlanReadiness` are covered. The portfolio and profile forms are not.
2. **`mypy app`** has never been run; the config exists in `pyproject.toml`.
3. **CI.** Backend and frontend checks are all single commands; a workflow running
   both on push is straightforward.
4. **`docker-compose.yml`** for Postgres + api + web.
5. **A real PSX provider** behind the existing `MarketDataProvider` interface. This
   is the change that turns the tool from a demonstration into something usable,
   and by design it touches no service, endpoint or test.
6. **Accessibility pass.** Controls are label-bound and focus is visible, but this
   has not been checked with a screen reader or axe.
7. **Backend suite takes ~2 minutes** — each API test loads 24 companies × 240
   price bars. A session-scoped seeded database would cut it.

## Not yet under git

Still true, and now more worth doing: there is a backend, a frontend and two
documents to import. Worth `git init` plus one initial commit before the next
change, so subsequent work reads as a diff.
