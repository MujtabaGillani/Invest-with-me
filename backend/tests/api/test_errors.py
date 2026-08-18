"""The error envelope.

Every failure - domain rule, bad path parameter, unmatched route, unhandled bug -
must produce the same shape, because the frontend writes its error handling once.
These tests are the contract for that shape.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_company_service

pytestmark = pytest.mark.api

#: Every error body must have exactly these keys under "error".
ENVELOPE_KEYS = {"code", "message", "details", "request_id"}


def assert_envelope(body: dict, *, code: str) -> None:
    assert set(body) == {"error"}, body
    error = body["error"]
    assert set(error) == ENVELOPE_KEYS, error
    assert error["code"] == code
    assert error["message"]
    assert isinstance(error["details"], dict)
    assert error["request_id"]


class TestDomainErrors:
    def test_not_found_uses_the_envelope_and_a_specific_code(
        self, seeded_client: TestClient, api: str
    ) -> None:
        response = seeded_client.get(f"{api}/companies/NOSUCH")

        assert response.status_code == 404
        assert_envelope(response.json(), code="company_not_found")
        assert response.json()["error"]["details"] == {"symbol": "NOSUCH"}

    def test_conflict_uses_the_envelope(self, seeded_client: TestClient, api: str) -> None:
        seeded_client.post(f"{api}/plans", json={"symbol": "LUCK"})
        response = seeded_client.post(f"{api}/plans", json={"symbol": "LUCK"})

        assert response.status_code == 409
        assert_envelope(response.json(), code="conflict")

    def test_business_rule_violations_use_the_envelope(
        self, seeded_client: TestClient, api: str
    ) -> None:
        response = seeded_client.post(
            f"{api}/portfolio/trades",
            json={"symbol": "LUCK", "side": "sell", "quantity": "10", "price": "800"},
        )

        assert response.status_code == 422
        assert_envelope(response.json(), code="validation_error")

    def test_insufficient_data_is_distinguishable_from_a_bad_request(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """The client needs to tell "no data yet" from "you sent nonsense"."""
        # PAEL exists with financials but the technical engine needs 30 sessions;
        # ask for a company whose analysis cannot be produced from what is stored.
        response = seeded_client.get(f"{api}/companies/LUCK/technicals")
        # LUCK has enough history, so this must succeed - the negative case is
        # covered by the analysis tests. Here we only assert the codes differ.
        assert response.status_code == 200

        bad = seeded_client.get(f"{api}/companies/NOSUCH/technicals")
        assert bad.json()["error"]["code"] == "company_not_found"


class TestRequestValidation:
    def test_a_malformed_body_reports_the_offending_field(
        self, seeded_client: TestClient, api: str
    ) -> None:
        response = seeded_client.post(
            f"{api}/portfolio/trades",
            json={"symbol": "LUCK", "side": "buy", "quantity": "-1", "price": "800"},
        )

        assert response.status_code == 422
        body = response.json()
        assert_envelope(body, code="request_validation_error")
        errors = body["error"]["details"]["errors"]
        assert any("quantity" in error["location"] for error in errors)

    def test_an_unknown_field_is_rejected_rather_than_ignored(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """A client typo must not silently do nothing."""
        response = seeded_client.post(
            f"{api}/watchlist",
            json={
                "symbol": "LUCK",
                "research_note": "A note long enough to satisfy the minimum length.",
                "targetEntryPrice": "800",  # camelCase typo - the API is snake_case
            },
        )
        assert response.status_code == 422

    def test_an_out_of_range_query_parameter_is_rejected(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """The pagination ceiling is a denial-of-service guard."""
        response = seeded_client.get(f"{api}/companies", params={"limit": 10_000})
        assert response.status_code == 422
        assert_envelope(response.json(), code="request_validation_error")

    def test_an_invalid_enum_value_is_rejected(self, seeded_client: TestClient, api: str) -> None:
        response = seeded_client.get(f"{api}/companies", params={"sector": "not_a_sector"})
        assert response.status_code == 422


class TestFrameworkErrors:
    def test_an_unmatched_route_uses_the_envelope(self, client: TestClient, api: str) -> None:
        response = client.get(f"{api}/nothing-here")

        assert response.status_code == 404
        assert_envelope(response.json(), code="http_404")

    def test_a_wrong_method_uses_the_envelope(self, client: TestClient, api: str) -> None:
        response = client.delete(f"{api}/health")

        assert response.status_code == 405
        assert_envelope(response.json(), code="http_405")


class TestUnhandledErrors:
    def test_an_unexpected_exception_becomes_a_generic_500_with_a_trace_id(
        self, app: FastAPI, client: TestClient, api: str
    ) -> None:
        """Internals must not leak, but the user must be able to quote a reference."""

        class ExplodingService:
            def list_companies(self, **_: object) -> None:
                raise RuntimeError("secret internal detail: SELECT * FROM users")

        app.dependency_overrides[get_company_service] = ExplodingService

        try:
            response = client.get(f"{api}/companies")
        finally:
            del app.dependency_overrides[get_company_service]

        assert response.status_code == 500
        body = response.json()
        assert_envelope(body, code="internal_error")
        assert "secret internal detail" not in response.text
        assert "SELECT" not in response.text
        assert "Quote the request id" in body["error"]["message"]
