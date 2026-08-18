"""HTTP middleware: correlation ids and request timing."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger, new_request_id, request_id_ctx

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
RESPONSE_TIME_HEADER = "X-Response-Time-ms"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a correlation id to the request and log its outcome.

    An inbound ``X-Request-ID`` is trusted and reused so a trace started by an
    upstream gateway or the frontend stays continuous; otherwise one is minted.
    The id is echoed on the response and included in every error envelope.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Logged here (with the id still bound) because the exception
            # handlers run outside this middleware's context on some paths.
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "%s %s failed after %.1fms", request.method, request.url.path, elapsed_ms
            )
            raise
        else:
            elapsed_ms = (time.perf_counter() - started) * 1000
            response.headers[REQUEST_ID_HEADER] = request_id
            response.headers[RESPONSE_TIME_HEADER] = f"{elapsed_ms:.1f}"
            logger.info(
                "%s %s -> %s (%.1fms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            return response
        finally:
            request_id_ctx.reset(token)
