"""Logging setup and request correlation.

Every request is tagged with an id (honouring an inbound ``X-Request-ID`` when
present) which is stored in a :class:`contextvars.ContextVar`. The log filter
injects it into every record, so a single grep reconstructs one request's full
server-side story - including logs emitted deep inside services that have no
access to the request object.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

#: Correlation id for the request currently being handled ("-" outside a request).
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id() -> str:
    """Generate a short, collision-safe correlation id."""
    return uuid.uuid4().hex[:16]


def get_request_id() -> str:
    """Return the current request's correlation id, or ``"-"`` if unset."""
    return request_id_ctx.get()


class RequestIdFilter(logging.Filter):
    """Attach ``record.request_id`` so formatters can reference it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    """Minimal structured formatter for log aggregators.

    Hand-rolled rather than pulling in a dependency: the field set is small and
    fixed, and this keeps the production image lean.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(*, level: str = "INFO", json_output: bool = False) -> None:
    """Install a single stdout handler on the root logger.

    Idempotent: existing handlers are replaced, so calling this from both the
    app factory and a test fixture cannot produce duplicated log lines.
    """
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        JsonFormatter()
        if json_output
        else logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Uvicorn ships its own handlers; clearing them makes it inherit ours so the
    # access log carries the same request id as application logs.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    """Convenience accessor so modules do not import ``logging`` directly."""
    return logging.getLogger(name)
