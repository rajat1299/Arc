import pytest
from factories import canonical_run_payload
from fastapi.testclient import TestClient
from opscanvas_api.app import create_app
from opscanvas_core.schema_versions import CURRENT_SCHEMA_VERSION


@pytest.fixture(autouse=True)
def use_memory_store_by_default(monkeypatch) -> None:
    monkeypatch.delenv("OPSCANVAS_API_STORE_BACKEND", raising=False)
    monkeypatch.delenv("OPSCANVAS_API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("OPSCANVAS_API_API_KEYS", raising=False)


def test_ingest_run_accepts_canonical_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/v1/ingest/runs", json=canonical_run_payload())

    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "run_id": "run_123",
        "schema_version": CURRENT_SCHEMA_VERSION,
        "span_count": 1,
        "event_count": 1,
    }


def test_ingest_run_rejects_unsupported_schema_version() -> None:
    client = TestClient(create_app())
    payload = canonical_run_payload()
    payload["schema_version"] = "999.0"

    response = client.post("/v1/ingest/runs", json=payload)

    assert response.status_code == 422
