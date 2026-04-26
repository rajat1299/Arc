from factories import canonical_run_payload
from fastapi.testclient import TestClient
from opscanvas_api.app import create_app
from opscanvas_core.schema_versions import CURRENT_SCHEMA_VERSION


def test_posted_run_is_queryable_by_id_and_spans() -> None:
    client = TestClient(create_app())
    payload = canonical_run_payload()

    ingest_response = client.post("/v1/ingest/runs", json=payload)
    run_response = client.get("/v1/runs/run_123")
    spans_response = client.get("/v1/runs/run_123/spans")

    assert ingest_response.status_code == 202
    assert run_response.status_code == 200
    assert run_response.json()["id"] == "run_123"
    assert run_response.json()["spans"][0]["input"] == {"query": "contract"}
    assert spans_response.status_code == 200
    assert spans_response.json() == run_response.json()["spans"]


def test_list_runs_returns_summaries_newest_first() -> None:
    client = TestClient(create_app())
    older = canonical_run_payload(id="run_old", started_at="2026-01-01T00:00:00Z")
    newer = canonical_run_payload(
        id="run_new",
        status="failed",
        runtime="claude-agent-sdk",
        started_at="2026-01-02T00:00:00Z",
        tenant_id="tenant_456",
        environment="prod",
        workflow_name="prod-workflow",
    )

    client.post("/v1/ingest/runs", json=older)
    client.post("/v1/ingest/runs", json=newer)

    response = client.get("/v1/runs")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "run_new",
            "schema_version": CURRENT_SCHEMA_VERSION,
            "status": "failed",
            "runtime": "claude-agent-sdk",
            "started_at": "2026-01-02T00:00:00Z",
            "ended_at": "2026-01-01T00:00:03Z",
            "tenant_id": "tenant_456",
            "environment": "prod",
            "workflow_name": "prod-workflow",
            "span_count": 1,
            "event_count": 1,
            "cost_usd": 0.02,
            "total_tokens": 18,
        },
        {
            "id": "run_old",
            "schema_version": CURRENT_SCHEMA_VERSION,
            "status": "succeeded",
            "runtime": "pytest",
            "started_at": "2026-01-01T00:00:00Z",
            "ended_at": "2026-01-01T00:00:03Z",
            "tenant_id": "tenant_123",
            "environment": "test",
            "workflow_name": "contract-test",
            "span_count": 1,
            "event_count": 1,
            "cost_usd": 0.02,
            "total_tokens": 18,
        },
    ]


def test_list_runs_filters_and_limits_summaries() -> None:
    client = TestClient(create_app())
    matching_old = canonical_run_payload(id="run_match_old", started_at="2026-01-01T00:00:00Z")
    matching_new = canonical_run_payload(id="run_match_new", started_at="2026-01-02T00:00:00Z")
    filtered_out = canonical_run_payload(
        id="run_other",
        status="running",
        runtime="langgraph",
        tenant_id="tenant_other",
        environment="dev",
        started_at="2026-01-03T00:00:00Z",
    )

    client.post("/v1/ingest/runs", json=matching_old)
    client.post("/v1/ingest/runs", json=matching_new)
    client.post("/v1/ingest/runs", json=filtered_out)

    response = client.get(
        "/v1/runs",
        params={
            "status": "succeeded",
            "runtime": "pytest",
            "tenant_id": "tenant_123",
            "environment": "test",
            "limit": 1,
        },
    )

    assert response.status_code == 200
    assert [run["id"] for run in response.json()] == ["run_match_new"]


def test_unknown_run_id_returns_clear_404() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/runs/missing_run")

    assert response.status_code == 404
    assert response.json() == {"detail": "Run 'missing_run' was not found."}


def test_duplicate_run_id_replaces_prior_run() -> None:
    client = TestClient(create_app())
    original = canonical_run_payload(id="run_replace", status="running")
    replacement = canonical_run_payload(
        id="run_replace",
        status="succeeded",
        workflow_name="replacement-workflow",
        usage={"total_tokens": 42, "cost_usd": 0.09},
    )

    client.post("/v1/ingest/runs", json=original)
    client.post("/v1/ingest/runs", json=replacement)

    run_response = client.get("/v1/runs/run_replace")
    list_response = client.get("/v1/runs")

    assert run_response.status_code == 200
    assert run_response.json()["workflow_name"] == "replacement-workflow"
    assert run_response.json()["usage"]["total_tokens"] == 42
    assert run_response.json()["usage"]["cost_usd"] == 0.09
    assert [run["id"] for run in list_response.json()] == ["run_replace"]
