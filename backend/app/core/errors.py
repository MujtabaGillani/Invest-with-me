"""Domain exceptions and their HTTP translation.

Services and repositories raise the exceptions defined here; they know nothing
about HTTP. A single set of handlers registered in :mod:`app.main` maps them to
a stable error envelope so clients can branch on ``error.code`` instead of
parsing prose.

Envelope shape (identical for every failure, including validation):

.. code-block:: json

    {
      "error": {
        "code": "company_not_found",
        "message": "No company found for symbol 'XYZ'.",
        "details": {"symbol": "XYZ"},
        "request_id": "3f8c..."
      }
    }
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for every expected (non-bug) failure in the application.

    :param message: Human-readable, safe to show to an end user.
    :param details: Machine-readable context; must not contain secrets.
    """

    #: Stable, snake_case identifier clients may switch on. Never renamed
    #: without a version bump.
    code: str = "internal_error"
    #: HTTP status the API layer should return.
    status_code: int = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    """A requested entity does not exist."""

    code = "not_found"
    status_code = 404


class CompanyNotFoundError(NotFoundError):
    code = "company_not_found"

    def __init__(self, symbol: str) -> None:
        super().__init__(f"No company found for symbol '{symbol}'.", details={"symbol": symbol})


class ConflictError(AppError):
    """The request cannot be applied to the current state of the resource."""

    code = "conflict"
    status_code = 409


class ValidationError(AppError):
    """Input is well-formed but violates a business rule.

    Distinct from FastAPI's request-shape validation (422): this is raised by
    services, e.g. selling more shares than are held.
    """

    code = "validation_error"
    status_code = 422


class InsufficientDataError(AppError):
    """Analysis was requested but the underlying history is too short.

    Returned rather than silently emitting a low-confidence verdict - the guide
    is explicit that partial data should prompt investigation, not a rating.
    """

    code = "insufficient_data"
    status_code = 422


class ProviderError(AppError):
    """A market-data provider failed or is not configured."""

    code = "provider_error"
    status_code = 502


def build_error_body(
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Assemble the canonical error envelope."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id,
        }
    }
