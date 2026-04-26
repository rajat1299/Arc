from fastapi.testclient import TestClient
from opscanvas_api.app import create_app
from opscanvas_core.schema_versions import CURRENT_SCHEMA_VERSION


def _canonical_run_payload() -> dict[str, object]:
    return {
        "id": "run_123",
        "schema_version": CURRENT_SCHEMA_VERSION,
        "status": "succeeded",
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:03Z",
        "runtime": "pytest",
        "project_id": "project_123",
        "environment": "test",
        "metadata": {"trace": "abc"},
        "spans": [
            {
                "id": "span_123",
                "run_id": "run_123",
                "kind": "tool_call",
                "name": "search",
                "started_at": "2026-01-01T00:00:01Z",
                "ended_at": "2026-01-01T00:00:02Z",
                "input": {"query": "contract"},
                "output": {"count": 1},
                "events": [
                    {
                        "id": "evt_123",
                        "span_id": "span_123",
                        "name": "tool.completed",
                        "timestamp": "2026-01-01T00:00:02Z",
                        "attributes": {"ok": True},
                    }
                ],
            }
        ],
    }


def test_ingest_run_accepts_canonical_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/v1/ingest/runs", json=_canonical_run_payload())

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
    payload = _canonical_run_payload()
    payload["schema_version"] = "999.0"

    response = client.post("/v1/ingest/runs", json=payload)

    assert response.status_code == 422
