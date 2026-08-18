# PSX Invest

A decision-support tool for evaluating Pakistan Stock Exchange (PSX) equities,
built from the process in *"Investing on PSX: A Beginner's Working Guide"*.

## What it does — and deliberately does not

It turns the guide's process into software:

| Guide section | Implemented as |
| --- | --- |
| 1. Start with your own goals | Investor profile: horizon, risk tolerance, position/sector limits, money-hygiene declarations, with derived warnings |
| 2. Fundamentals checklist | Seven metrics scored against stated criteria, each with peer-relative context where the guide asks for it |
| 3. The three statements | Four plain-language checks, with the guide's "two or more no's" investigation rule |
| 4. Technical signals | Trend, RSI(14), 50/200-day MAs, volume confirmation — framed as timing context, personalised to your horizon |
| 5. Deciding when to buy | Five-question pre-buy checklist plus position sizing against your own limits |
| 6. Deciding when to sell | Profit target and stop-loss committed **before** buying, plus a thesis review journal |
| 7. Common mistakes | Research notes required before watching; falling-knife detection; concentration warnings |
| 8. Verify data yourself | Every response carries provenance and links to PSX/Sarmaaya/SCSTrade |

**There is no endpoint that returns a rating, a price target, or a buy/sell
signal.** That is a product constraint, not a gap. The guide's own opening point
is that no model can reliably predict short-term price moves, so the software
scores stated criteria and records your decisions — it never makes them.

> ⚠️ **The bundled dataset is synthetic.** Ticker symbols, company names and
> sectors are real PSX listings; every financial figure and price is generated for
> demonstration. `GET /api/v1/meta` reports `provider.is_synthetic: true`, and the
> UI must label the data accordingly. See [Market data](#market-data).

## Layout

```
psx-invest/
├── backend/                  FastAPI + SQLAlchemy 2.0 + Pydantic v2
│   ├── app/
│   │   ├── core/             config, logging, errors, enums, clock, numeric helpers
│   │   ├── db/               declarative base, session lifecycle, seeding
│   │   ├── models/           ORM models (one file per aggregate)
│   │   ├── schemas/          Pydantic request/response contracts
│   │   ├── repositories/     all SQL lives here; no business rules
│   │   ├── analysis/         pure engines — no ORM, no FastAPI, fully unit-tested
│   │   ├── providers/        market data seam (interface + seeded implementation)
│   │   ├── services/         business rules and transaction boundaries
│   │   ├── api/v1/           routers and endpoint handlers
│   │   └── main.py           application factory, lifespan, error handlers
│   ├── alembic/              migrations (authoritative for the schema)
│   └── tests/                unit/ (pure logic) and api/ (HTTP end to end)
├── frontend/                 React 19 + Vite + TypeScript + TanStack Query + Tailwind 4
│   ├── openapi.json          exported from the backend; types are generated from it
│   └── src/
│       ├── types/            api.d.ts (generated) + readable aliases over it
│       ├── lib/              api client, query keys/config, formatters
│       ├── components/ui/    presentation primitives
│       ├── components/layout/ app shell, synthetic-data banner
│       ├── features/         one folder per domain area: queries + its components
│       └── pages/            one per route
└── docs/                     architecture notes and status
```

The import direction is one-way and enforced by review:

```
api → services → repositories → models
               → analysis (pure)
               → providers
```

## Running the backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -e ".[dev]"

cp .env.example .env            # optional — every default already works

uvicorn app.main:app --reload
```

Then open <http://localhost:8000/docs>.

On first start the app creates a SQLite database (`psx_invest.db`), loads 24
companies with five years of statements and ~320 sessions of price history each,
and creates a demo portfolio, plans and watchlist. It is idempotent — restarting
will not duplicate anything.

## Running the frontend

With the backend already running:

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

The dev server proxies `/api` to `http://127.0.0.1:8000`, so requests stay
same-origin in development and behave as they will behind a reverse proxy.

### Types are generated, never hand-written

The frontend's API types come from the backend's own OpenAPI schema, so the two
cannot drift:

```bash
cd backend && python scripts/export_openapi.py   # writes frontend/openapi.json
cd ../frontend && npm run codegen                # regenerates src/types/api.d.ts
```

Both files are committed, so the frontend builds without the backend running and
any contract change shows up as a reviewable diff. Application code imports from
[`src/types/index.ts`](frontend/src/types/index.ts), which aliases the generated
types under readable names.

### Frontend commands

```bash
npm run dev            # dev server
npm run build          # typecheck (project references) + production bundle
npm run typecheck      # tsc only
npm run lint           # eslint, type-aware
npm run format         # prettier
npm test               # vitest
npm run test:coverage
```

### Backend commands

```bash
pytest                              # 344 tests
pytest -m unit                      # pure logic only, no database
pytest --cov                        # with coverage

ruff check app tests alembic        # lint
ruff format app tests alembic       # format
mypy app                            # type check

python -m app.db.seed --reset       # rebuild the database from scratch
python -m app.db.seed --no-demo-data

alembic upgrade head                        # apply migrations
alembic revision --autogenerate -m "note"   # generate one (then READ it)
```

## Configuration

Every setting is an environment variable prefixed `PSX_`, read once through
`app.core.config.get_settings()`. See [`backend/.env.example`](backend/.env.example)
for the full list. Notable ones:

| Variable | Default | Notes |
| --- | --- | --- |
| `PSX_DATABASE_URL` | `sqlite+pysqlite:///./psx_invest.db` | Postgres needs no code change: `postgresql+psycopg://…` |
| `PSX_MARKET_DATA_PROVIDER` | `seeded` | The only value registered today |
| `PSX_AUTO_MIGRATE` / `PSX_SEED_ON_STARTUP` | `true` | Ignored in production, where Alembic owns the schema |
| `PSX_DEFAULT_USER_EMAIL` | `investor@example.com` | v1 is single-user; see below |

## Market data

All external data arrives through one interface,
[`MarketDataProvider`](backend/app/providers/base.py). Services depend on the
protocol, never on an implementation, so replacing the bundled dataset with a live
PSX feed, a broker API or a CSV importer means writing one class and adding one
line to `providers/registry.py` — no service, endpoint or test changes.

Two providers ship, selected with `PSX_MARKET_DATA_PROVIDER`:

| Value | Data |
| --- | --- |
| `seeded` (default) | The bundled illustrative dataset. `is_synthetic: true`. |
| `psx` | **Real PSX data.** `is_synthetic: false`, `price_delay_minutes: 15`. |

The bundled `SeededMarketDataProvider` generates deterministic data from compact
company profiles in `app/data/seed_companies.json`. It reports
`is_synthetic: true`, which propagates through `/meta` and the portfolio response
so the client can never present generated figures as real. The dataset
deliberately includes a falling knife (DGKC), a loss-maker with no meaningful P/E
(TRG), a bank whose gearing must be judged against peers (HBL) and a profitable
company burning cash (UNITY), so every branch of the analysis engines is exercised
by the demo data itself.

### Real PSX data

```bash
pip install -e ".[psx]"                 # psxdata + parser deps, ~50 MB
export PSX_MARKET_DATA_PROVIDER=psx
```

`PsxDataProvider` composes two upstreams: the MIT-licensed `psxdata` library for
listings and daily OHLCV, and the PSX Data Portal company pages for annual Sales,
Profit after Taxation and EPS. Verified against real listings — 740 equities
filtered from 1,002 raw symbols (debt instruments and ETFs excluded).

**It covers four of the seven fundamentals metrics.** Revenue growth, net margin,
EPS trend and P/E work. Debt-to-equity, free cash flow and dividends report
`insufficient_data`, because no free source publishes the balance sheet or the
cash flow statement. That is the honest outcome rather than a guess — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §15.

Three caveats the UI surfaces rather than hides:

- **Prices are delayed by at least 15 minutes.** Real-time PSX data requires a
  licence from the exchange. The banner says so whenever
  `price_delay_minutes` is not `0` (§16).
- **Prices and EPS are unadjusted** for bonus issues and splits. An EPS series
  spanning a share-count change is reported as not comparable rather than as a
  decline (§17).
- **Terms of use.** PSX prohibits redistribution and commercial use of its market
  data without a licence (`marketdatarequest@psx.com.pk`). Reading the public site
  for your own research is a different matter from republishing it.

## Authentication

**v1 has none, by design.** `app/api/deps.py::get_current_user` resolves one
account from configuration for every request. Every user-owned table already
carries `user_id` and every per-user query is scoped by it, so adding real
authentication is a change to that single function. It is safe only because the
service is intended to run locally for one person.

## Further reading

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — design decisions and their rationale
- [`docs/STATUS.md`](docs/STATUS.md) — what is built, what is next
- `app/analysis/rules.py` — every threshold that turns the guide's qualitative
  advice into a check, with the reasoning for each number

---

*This software is educational. It is not financial advice, and following its
output does not guarantee profit or protect against loss.*
