import sys
from types import SimpleNamespace

import pytest
from factories import canonical_run_payload
from fastapi.testclient import TestClient
from opscanvas_api.app import create_app
from opscanvas_api.store import ClickHouseRunStore, InMemoryRunStore
from opscanvas_core.schema_versions import CURRENT_SCHEMA_VERSION


@pytest.fixture(autouse=True)
def use_memory_store_by_default(monkeypatch) -> None:
    monkeypatch.delenv("OPSCANVAS_API_STORE_BACKEND", raising=False)
    monkeypatch.delenv("OPSCANVAS_API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("OPSCANVAS_API_API_KEYS", raising=False)


def test_create_app_uses_memory_store_by_default(monkeypatch) -> None:
    monkeypatch.delenv("OPSCANVAS_API_STORE_BACKEND", raising=False)

    app = create_app()

    assert isinstance(app.state.run_store, InMemoryRunStore)


def test_create_app_uses_clickhouse_store_when_configured(monkeypatch) -> None:
    captured_kwargs = {}
    fake_client = object()

    def get_client(**kwargs):
        captured_kwargs.update(kwargs)
        return fake_client

    monkeypatch.setenv("OPSCANVAS_API_STORE_BACKEND", "clickhouse")
    monkeypatch.setenv("OPSCANVAS_API_CLICKHOUSE_HOST", "clickhouse.local")
    monkeypatch.setenv("OPSCANVAS_API_CLICKHOUSE_PORT", "9440")
    monkeypatch.setenv("OPSCANVAS_API_CLICKHOUSE_USERNAME", "api_user")
    monkeypatch.setenv("OPSCANVAS_API_CLICKHOUSE_PASSWORD", "api_password")
    monkeypatch.setenv("OPSCANVAS_API_CLICKHOUSE_DATABASE", "api_db")
    monkeypatch.setenv("OPSCANVAS_API_CLICKHOUSE_SECURE", "true")
    monkeypatch.setitem(
        sys.modules,
        "clickhouse_connect",
        SimpleNamespace(get_client=get_client),
    )

    app = create_app()

    assert isinstance(app.state.run_store, ClickHouseRunStore)
    assert captured_kwargs == {}

    resolved_client = app.state.run_store._client._resolve()

    assert resolved_client is fake_client
    assert captured_kwargs == {
        "host": "clickhouse.local",
        "port": 9440,
        "username": "api_user",
        "password": "api_password",
        "database": "api_db",
        "secure": True,
    }


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


def test_reported_run_cost_wins_over_computed_span_cost() -> None:
    client = TestClient(create_app())
    payload = canonical_run_payload(
        usage={"total_tokens": 3_000, "cost_usd": 0.02},
        spans=[
            {
                "id": "span_reported_wins",
                "run_id": "run_123",
                "kind": "model_call",
                "name": "model",
                "started_at": "2026-01-01T00:00:01Z",
                "ended_at": "2026-01-01T00:00:02Z",
                "usage": {"input_tokens": 1_000, "output_tokens": 2_000},
                "attributes": {"provider": "openai", "model": "gpt-5.4-mini"},
            }
        ],
    )

    assert client.post("/v1/ingest/runs", json=payload).status_code == 202

    list_response = client.get("/v1/runs")
    metrics_response = client.get("/v1/runs/metrics")

    assert list_response.json()[0]["cost_usd"] == 0.02
    assert metrics_response.json()["total_cost_usd"] == 0.02


def test_missing_run_cost_is_computed_from_openai_span_usage() -> None:
    client = TestClient(create_app())
    payload = canonical_run_payload(
        usage={"total_tokens": 3_000},
        spans=[
            {
                "id": "span_openai_cost",
                "run_id": "run_123",
                "kind": "model_call",
                "name": "model",
                "started_at": "2026-01-01T00:00:01Z",
                "ended_at": "2026-01-01T00:00:02Z",
                "usage": {"input_tokens": 1_000, "output_tokens": 2_000},
                "attributes": {"provider": "openai", "model": "gpt-5.4-mini"},
            }
        ],
    )

    assert client.post("/v1/ingest/runs", json=payload).status_code == 202

    list_response = client.get("/v1/runs")
    metrics_response = client.get("/v1/runs/metrics")
    run_response = client.get("/v1/runs/run_123")

    assert list_response.json()[0]["cost_usd"] == 0.00975
    assert metrics_response.json()["total_cost_usd"] == 0.00975
    assert run_response.json()["usage"]["cost_usd"] is None


def test_openai_agents_runtime_infers_openai_provider_for_span_cost() -> None:
    client = TestClient(create_app())
    payload = canonical_run_payload(
        runtime="openai-agents",
        usage={"total_tokens": 3_000},
        spans=[
            {
                "id": "span_inferred_provider",
                "run_id": "run_123",
                "kind": "model_call",
                "name": "model",
                "started_at": "2026-01-01T00:00:01Z",
                "ended_at": "2026-01-01T00:00:02Z",
                "usage": {"input_tokens": 1_000, "output_tokens": 2_000},
                "attributes": {"agent.model": "gpt-5.4-mini"},
            }
        ],
    )

    assert client.post("/v1/ingest/runs", json=payload).status_code == 202

    response = client.get("/v1/runs")

    assert response.json()[0]["cost_usd"] == 0.00975


def test_unknown_model_with_missing_run_cost_stays_unpriced() -> None:
    client = TestClient(create_app())
    payload = canonical_run_payload(
        usage={"total_tokens": 3_000},
        spans=[
            {
                "id": "span_unknown_model",
                "run_id": "run_123",
                "kind": "model_call",
                "name": "model",
                "started_at": "2026-01-01T00:00:01Z",
                "ended_at": "2026-01-01T00:00:02Z",
                "usage": {"input_tokens": 1_000, "output_tokens": 2_000},
                "attributes": {"provider": "openai", "model": "gpt-unknown"},
            }
        ],
    )

    assert client.post("/v1/ingest/runs", json=payload).status_code == 202

    list_response = client.get("/v1/runs")
    metrics_response = client.get("/v1/runs/metrics")

    assert list_response.json()[0]["cost_usd"] is None
    assert metrics_response.json()["total_cost_usd"] == 0.0


def test_run_metrics_are_empty_for_empty_store() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/runs/metrics")

    assert response.status_code == 200
    assert response.json() == {
        "run_count": 0,
        "failed_count": 0,
        "running_count": 0,
        "suboptimal_count": 0,
        "total_cost_usd": 0.0,
        "total_tokens": 0,
        "p95_latency_ms": None,
    }


def test_run_metrics_aggregate_mixed_in_memory_runs() -> None:
    client = TestClient(create_app())
    runs = [
        canonical_run_payload(
            id="run_succeeded",
            status="succeeded",
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:01Z",
            usage={"total_tokens": 10, "cost_usd": 0.01},
        ),
        canonical_run_payload(
            id="run_failed",
            status="failed",
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:03Z",
            usage={"total_tokens": 20, "cost_usd": 0.02},
        ),
        canonical_run_payload(
            id="run_suboptimal",
            status="suboptimal",
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:07Z",
            usage={"total_tokens": 30, "cost_usd": 0.03},
        ),
        canonical_run_payload(
            id="run_running",
            status="running",
            started_at="2026-01-01T00:00:00Z",
            ended_at=None,
            usage=None,
        ),
    ]

    for run in runs:
        ingest_response = client.post("/v1/ingest/runs", json=run)
        assert ingest_response.status_code == 202

    response = client.get("/v1/runs/metrics")

    assert response.status_code == 200
    assert response.json() == {
        "run_count": 4,
        "failed_count": 1,
        "running_count": 1,
        "suboptimal_count": 1,
        "total_cost_usd": 0.06,
        "total_tokens": 60,
        "p95_latency_ms": 7000,
    }


def test_run_metrics_aggregate_mixed_reported_computed_and_unpriced_costs() -> None:
    client = TestClient(create_app())
    runs = [
        canonical_run_payload(
            id="run_reported",
            usage={"total_tokens": 10, "cost_usd": 0.02},
        ),
        canonical_run_payload(
            id="run_computed",
            usage={"total_tokens": 3_000},
            spans=[
                {
                    "id": "span_computed",
                    "run_id": "run_computed",
                    "kind": "model_call",
                    "name": "model",
                    "started_at": "2026-01-01T00:00:01Z",
                    "ended_at": "2026-01-01T00:00:02Z",
                    "usage": {"input_tokens": 1_000, "output_tokens": 2_000},
                    "attributes": {"provider": "openai", "model": "gpt-5.4-mini"},
                }
            ],
        ),
        canonical_run_payload(
            id="run_unpriced",
            usage={"total_tokens": 3_000},
            spans=[
                {
                    "id": "span_unpriced",
                    "run_id": "run_unpriced",
                    "kind": "model_call",
                    "name": "model",
                    "started_at": "2026-01-01T00:00:01Z",
                    "ended_at": "2026-01-01T00:00:02Z",
                    "usage": {"input_tokens": 1_000, "output_tokens": 2_000},
                    "attributes": {"provider": "openai", "model": "gpt-unknown"},
                }
            ],
        ),
    ]

    for run in runs:
        assert client.post("/v1/ingest/runs", json=run).status_code == 202

    response = client.get("/v1/runs/metrics")

    assert response.json()["total_cost_usd"] == 0.02975


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
