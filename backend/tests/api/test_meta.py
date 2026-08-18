"""Health and metadata endpoints.

``/meta`` is the contract that stops the frontend keeping a second copy of the
server's vocabulary, and the channel through which it learns whether the data is
real. Both are asserted here because a silent regression in either would show up
as a mislabelled UI rather than as a failure.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.core.enums import MetricVerdict, RiskTolerance, Sector, TimeHorizon
from app.schemas.plans import CHECKLIST_QUESTIONS

pytestmark = pytest.mark.api


class TestHealth:
    def test_reports_ok_with_a_reachable_database(self, client: TestClient, api: str) -> None:
        response = client.get(f"{api}/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["database_reachable"] is True
        assert body["version"] == __version__
        assert body["environment"] == "local"

    def test_every_response_carries_a_correlation_id(self, client: TestClient, api: str) -> None:
        """One grep reconstructs a request's whole server-side story."""
        response = client.get(f"{api}/health")

        assert response.headers["X-Request-ID"]
        assert float(response.headers["X-Response-Time-ms"]) >= 0

    def test_an_inbound_correlation_id_is_honoured(self, client: TestClient, api: str) -> None:
        """A trace started by a gateway or the frontend must stay continuous."""
        response = client.get(f"{api}/health", headers={"X-Request-ID": "trace-from-upstream"})
        assert response.headers["X-Request-ID"] == "trace-from-upstream"


class TestMetadata:
    def test_reports_the_active_provider_and_its_provenance(
        self, client: TestClient, api: str
    ) -> None:
        provider = client.get(f"{api}/meta").json()["provider"]

        assert provider["name"] == "seeded"
        assert provider["is_synthetic"] is True
        assert "must not be used for real investment decisions" in provider["description"]
        # Guide section 8: tell the user where to check the real figures.
        assert any("psx.com.pk" in source for source in provider["verification_sources"])

    def test_exposes_every_enum_the_client_renders(self, client: TestClient, api: str) -> None:
        body = client.get(f"{api}/meta").json()

        assert {item["value"] for item in body["sectors"]} == {item.value for item in Sector}
        assert {item["value"] for item in body["time_horizons"]} == {
            item.value for item in TimeHorizon
        }
        assert {item["value"] for item in body["risk_tolerances"]} == {
            item.value for item in RiskTolerance
        }
        assert {item["value"] for item in body["metric_verdicts"]} == {
            item.value for item in MetricVerdict
        }

    def test_every_option_has_a_human_label(self, client: TestClient, api: str) -> None:
        body = client.get(f"{api}/meta").json()
        for group in ("sectors", "time_horizons", "risk_tolerances", "metric_verdicts"):
            assert all(item["label"] for item in body[group]), group

    def test_the_prebuy_checklist_wording_is_served_not_duplicated(
        self, client: TestClient, api: str
    ) -> None:
        checklist = client.get(f"{api}/meta").json()["prebuy_checklist"]

        assert [item["value"] for item in checklist] == list(CHECKLIST_QUESTIONS)
        assert len(checklist) == 5
        assert all(item["label"].endswith("?") for item in checklist)

    def test_insufficient_data_is_labelled_as_distinct_from_a_bad_result(
        self, client: TestClient, api: str
    ) -> None:
        verdicts = {
            item["value"]: item for item in client.get(f"{api}/meta").json()["metric_verdicts"]
        }
        assert "Not the same as a bad result" in verdicts["insufficient_data"]["description"]

    def test_the_disclaimer_travels_with_the_data(self, client: TestClient, api: str) -> None:
        disclaimer = client.get(f"{api}/meta").json()["disclaimer"]
        assert disclaimer["is_financial_advice"] is False
        assert "Nothing here is financial advice" in disclaimer["text"]
        assert "do not predict price movements" in disclaimer["text"]


class TestOpenApi:
    def test_the_schema_documents_every_route(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        for expected in (
            "/api/v1/health",
            "/api/v1/meta",
            "/api/v1/companies",
            "/api/v1/companies/{symbol}/fundamentals",
            "/api/v1/companies/{symbol}/technicals",
            "/api/v1/profile",
            "/api/v1/watchlist",
            "/api/v1/plans",
            "/api/v1/plans/{plan_id}/commit",
            "/api/v1/portfolio",
            "/api/v1/portfolio/trades",
            "/api/v1/alerts/evaluate",
        ):
            assert expected in paths, expected

    def test_no_endpoint_offers_a_recommendation(self, client: TestClient) -> None:
        """A structural guard on the product constraint.

        If somebody ever adds ``/recommendations`` or a ``rating`` field, this fails
        - which is the point. The constraint is a requirement, not a preference.
        """
        schema = client.get("/openapi.json").json()
        paths = " ".join(schema["paths"]).lower()
        for forbidden in ("recommend", "signal", "rating", "prediction", "forecast"):
            assert forbidden not in paths, forbidden
