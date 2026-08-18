"""Application factory, lifespan and exception handlers.

Built as a factory (:func:`create_app`) rather than a module-level ``app``
singleton so tests can construct an application with overridden settings, and so
nothing happens at import time.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1.router import build_api_router
from app.core.config import Settings, get_settings
from app.core.errors import AppError, build_error_body
from app.core.logging import configure_logging, get_logger, get_request_id
from app.core.middleware import RequestContextMiddleware
from app.providers.registry import build_provider

logger = get_logger(__name__)

DESCRIPTION = """
Decision-support API for evaluating Pakistan Stock Exchange (PSX) equities.

**What this API does:** scores a company against a fixed, published fundamentals
checklist; reports technical readings as timing context; records the pre-buy
checklist, profit target and stop-loss you commit to *before* buying; tracks your
portfolio against the diversification limits you set for yourself; and tells you
when one of your own rules has been crossed.

**What it does not do:** predict prices, rate stocks, or tell you what to buy or
sell. There is no endpoint that returns a recommendation, and that is a deliberate
product constraint rather than a missing feature.

Check `GET /api/v1/meta` for `provider.is_synthetic`. When it is `true`, every
financial figure and price served by this API is **generated demonstration data**
for real PSX ticker symbols - useful for exercising the application, useless for
real decisions.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start-up and shut-down work.

    Binds the market data provider once (it may hold a client and a cache) and,
    when configured to, ensures the schema and seed data exist. Provider
    construction failures are fatal by design: a running API with no data source
    would answer every request with an unexplained error.
    """
    settings: Settings = app.state.settings

    app.state.market_data_provider = build_provider(settings)
    logger.info(
        "Market data provider '%s' bound (synthetic=%s).",
        app.state.market_data_provider.metadata.name,
        app.state.market_data_provider.metadata.is_synthetic,
    )

    if settings.auto_migrate or settings.seed_on_startup:
        if settings.is_production:
            # Guard rail, not a preference: create_all cannot express a column
            # rename or a backfill, so a production schema must come from Alembic.
            logger.error(
                "auto_migrate/seed_on_startup are set in production and will be ignored. "
                "Run 'alembic upgrade head' as a deployment step instead."
            )
        else:
            # Imported here so a production process never pulls in the seeding
            # module or its demo data at all.
            from app.db.seed import create_schema, seed

            if settings.seed_on_startup:
                # seed() ensures the schema itself, so calling create_schema here
                # as well would just log the same line twice.
                seed(reset=False, include_demo_data=True)
            elif settings.auto_migrate:
                create_schema()

    logger.info(
        "%s v%s ready in '%s' environment.", settings.app_name, __version__, settings.environment
    )
    yield
    logger.info("Shutting down.")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    :param settings: injected for tests; falls back to the process settings.
    """
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=__version__,
        docs_url=settings.docs_url,
        redoc_url=None,
        openapi_url=settings.openapi_url,
        lifespan=lifespan,
    )
    # Stored on state so the lifespan and any handler can reach the same instance
    # the factory was given, rather than re-reading the environment.
    app.state.settings = settings

    _register_middleware(app, settings)
    _register_exception_handlers(app)
    app.include_router(build_api_router(settings), prefix=settings.api_v1_prefix)

    return app


def _register_middleware(app: FastAPI, settings: Settings) -> None:
    """Install CORS and request-context middleware.

    Order matters: middleware runs outermost-first in registration order, so the
    request-context middleware is added last and therefore wraps closest to the
    application - meaning a correlation id is bound before any handler runs.
    """
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            # Exposed so the browser can read the correlation id and the frontend
            # can surface it in an error report.
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "X-Response-Time-ms"],
        )
    app.add_middleware(RequestContextMiddleware)


def _register_exception_handlers(app: FastAPI) -> None:
    """Map every failure onto one error envelope.

    Clients get the same shape whether the failure was a domain rule, a bad path
    parameter or an unhandled bug, so error handling on the frontend is written
    once. See :mod:`app.core.errors`.
    """

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        """Expected domain failures: 404, 409, 422, 502."""
        logger.info("Domain error %s: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_body(
                exc.code, exc.message, details=exc.details, request_id=get_request_id()
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        """Malformed request bodies and query parameters.

        Pydantic's error list is passed through under ``details.errors`` so a form
        can highlight the offending field, but it is wrapped in the standard
        envelope rather than replacing it.
        """
        return JSONResponse(
            status_code=422,
            content=build_error_body(
                "request_validation_error",
                "The request could not be processed as sent.",
                # ``jsonable_encoder`` equivalent: Pydantic v2 errors can contain
                # exception instances in ``ctx``, which json.dumps cannot encode.
                details={"errors": _serialisable_errors(exc)},
                request_id=get_request_id(),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Framework-raised HTTP errors, e.g. an unmatched route."""
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_body(
                f"http_{exc.status_code}", str(exc.detail), request_id=get_request_id()
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        """Anything unanticipated.

        The exception is logged with its stack trace and correlation id; the client
        gets a generic message plus that id. Leaking the exception text would risk
        exposing query fragments or file paths.
        """
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=build_error_body(
                "internal_error",
                "Something went wrong handling this request. Quote the request id if you report "
                "it.",
                request_id=get_request_id(),
            ),
        )


def _serialisable_errors(exc: RequestValidationError) -> list[dict[str, object]]:
    """Reduce Pydantic validation errors to JSON-safe dictionaries."""
    return [
        {
            "location": list(error.get("loc", ())),
            "message": error.get("msg", ""),
            "type": error.get("type", ""),
        }
        for error in exc.errors()
    ]


#: ASGI entry point for ``uvicorn app.main:app``.
app = create_app()
