from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from opscanvas_api.store import ClickHouseRunStore
from opscanvas_core.events import Run, RunStatus, Span, SpanEvent, SpanKind, Usage
from opscanvas_core.schema_versions import CURRENT_SCHEMA_VERSION


class FakeQueryResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def named_results(self) -> list[dict[str, Any]]:
        return self._rows


class FakeClickHouseClient:
    def __init__(self, query_results: list[list[dict[str, Any]]] | None = None) -> None:
        self.commands: list[tuple[str, dict[str, Any] | None]] = []
        self.inserts: list[tuple[str, list[list[Any]], list[str]]] = []
        self.queries: list[tuple[str, dict[str, Any] | None]] = []
        self._query_results = list(query_results or [])

    def command(self, query: str, parameters: dict[str, Any] | None = None) -> None:
        self.commands.append((query, parameters))

    def insert(
        self,
        table: str,
        data: list[list[Any]],
        column_names: list[str],
    ) -> None:
        self.inserts.append((table, data, column_names))

    def query(self, query: str, parameters: dict[str, Any] | None = None) -> FakeQueryResult:
        self.queries.append((query, parameters))
        return FakeQueryResult(self._query_results.pop(0))


def test_upsert_replaces_existing_rows_and_inserts_expected_columns() -> None:
    client = FakeClickHouseClient()
    store = ClickHouseRunStore(client)
    run = _canonical_run()

    store.upsert(run)

    assert client.commands == [
        (
            "ALTER TABLE span_events DELETE WHERE run_id = {run_id:String} "
            "SETTINGS mutations_sync = 1",
            {"run_id": "run_123"},
        ),
        (
            "ALTER TABLE spans DELETE WHERE run_id = {run_id:String} "
            "SETTINGS mutations_sync = 1",
            {"run_id": "run_123"},
        ),
        (
            "ALTER TABLE runs DELETE WHERE run_id = {run_id:String} "
            "SETTINGS mutations_sync = 1",
            {"run_id": "run_123"},
        ),
    ]
    assert [insert[0] for insert in client.inserts] == ["runs", "spans", "span_events"]
    run_table, run_rows, run_columns = client.inserts[0]
    span_table, span_rows, span_columns = client.inserts[1]
    event_table, event_rows, event_columns = client.inserts[2]

    assert run_table == "runs"
    assert run_columns == [
        "org_id",
        "project_id",
        "environment_id",
        "run_id",
        "schema_version",
        "runtime",
        "status",
        "started_at",
        "ended_at",
        "duration_ms",
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "audio_input_tokens",
        "audio_output_tokens",
        "total_tokens",
        "batch_discount_multiplier",
        "cost_usd",
        "tenant_id",
        "user_id",
        "workflow_name",
        "metadata_json",
        "runtime_attributes_json",
    ]
    assert run_rows[0][run_columns.index("run_id")] == "run_123"
    assert run_rows[0][run_columns.index("metadata_json")] == (
        '{"org_id":"123e4567-e89b-12d3-a456-426614174111"}'
    )

    assert span_table == "spans"
    assert span_columns == [
        "org_id",
        "project_id",
        "environment_id",
        "run_id",
        "span_id",
        "parent_span_id",
        "kind",
        "name",
        "started_at",
        "ended_at",
        "duration_ms",
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "audio_input_tokens",
        "audio_output_tokens",
        "total_tokens",
        "batch_discount_multiplier",
        "cost_usd",
        "input_json",
        "output_json",
        "attributes_json",
        "runtime",
        "provider",
        "model",
        "tool_name",
        "service_tier",
    ]
    assert span_rows[0][span_columns.index("span_id")] == "span_model"
    assert span_rows[0][span_columns.index("input_json")] == '{"prompt":"hello"}'

    assert event_table == "span_events"
    assert event_columns == [
        "org_id",
        "project_id",
        "environment_id",
        "run_id",
        "span_id",
        "event_id",
        "name",
        "timestamp",
        "attributes_json",
    ]
    assert event_rows[0][event_columns.index("event_id")] == "evt_token"


def test_get_reconstructs_run_with_spans_events_json_usage_and_decimal_costs() -> None:
    client = FakeClickHouseClient(
        [
            [_run_row()],
            [_span_row()],
            [_event_row()],
        ]
    )
    store = ClickHouseRunStore(client)

    run = store.get("run_123")

    assert run == _canonical_run()
    assert run is not None
    dumped = run.model_dump(mode="json", by_alias=True)
    assert dumped["spans"][0]["input"] == {"prompt": "hello"}
    assert dumped["spans"][0]["output"] == {"text": "world"}
    assert run.usage == Usage(input_tokens=10, output_tokens=20, total_tokens=30, cost_usd=0.02)
    assert run.spans[0].usage == Usage(
        input_tokens=10,
        output_tokens=20,
        cached_input_tokens=3,
        reasoning_tokens=4,
        total_tokens=30,
        cost_usd=0.01,
    )
    assert client.queries[0][1] == {"run_id": "run_123"}


def test_get_returns_none_for_missing_run_without_extra_queries() -> None:
    client = FakeClickHouseClient([[]])
    store = ClickHouseRunStore(client)

    assert store.get("missing") is None

    assert len(client.queries) == 1
    assert client.queries[0][1] == {"run_id": "missing"}


def test_list_applies_filters_limit_and_newest_first_ordering() -> None:
    newer_row = {
        **_run_row(),
        "run_id": "run_new",
        "started_at": datetime(2026, 1, 2, tzinfo=UTC),
    }
    client = FakeClickHouseClient(
        [
            [newer_row, _run_row()],
            [_span_row(run_id="run_new"), _span_row()],
            [_event_row(run_id="run_new"), _event_row()],
        ]
    )
    store = ClickHouseRunStore(client)

    runs = store.list(
        status=RunStatus.succeeded,
        runtime="pytest",
        tenant_id="tenant_123",
        environment="123e4567-e89b-12d3-a456-426614174222",
        limit=2,
    )

    assert [run.id for run in runs] == ["run_new", "run_123"]
    assert [len(run.spans[0].events) for run in runs] == [1, 1]
    query, parameters = client.queries[0]
    assert "status = {status:String}" in query
    assert "runtime = {runtime:String}" in query
    assert "tenant_id = {tenant_id:String}" in query
    assert "environment_id = {environment:String}" in query
    assert "ORDER BY started_at DESC" in query
    assert "LIMIT {limit:UInt64}" in query
    assert parameters == {
        "status": "succeeded",
        "runtime": "pytest",
        "tenant_id": "tenant_123",
        "environment": "123e4567-e89b-12d3-a456-426614174222",
        "limit": 2,
    }


def _canonical_run() -> Run:
    return Run(
        id="run_123",
        schema_version=CURRENT_SCHEMA_VERSION,
        status=RunStatus.succeeded,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        ended_at=datetime(2026, 1, 1, 0, 0, 3, tzinfo=UTC),
        runtime="pytest",
        project_id="123e4567-e89b-12d3-a456-426614174000",
        environment="123e4567-e89b-12d3-a456-426614174222",
        tenant_id="tenant_123",
        user_id="user_123",
        workflow_name="workflow",
        usage=Usage(input_tokens=10, output_tokens=20, total_tokens=30, cost_usd=0.02),
        metadata={"org_id": "123e4567-e89b-12d3-a456-426614174111"},
        spans=[
            Span(
                id="span_model",
                run_id="run_123",
                kind=SpanKind.model_call,
                name="call model",
                started_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
                ended_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
                usage=Usage(
                    input_tokens=10,
                    output_tokens=20,
                    cached_input_tokens=3,
                    reasoning_tokens=4,
                    total_tokens=30,
                    cost_usd=0.01,
                ),
                input={"prompt": "hello"},
                output={"text": "world"},
                attributes={"provider": "openai", "model": "gpt-5.4"},
                events=[
                    SpanEvent(
                        id="evt_token",
                        span_id="span_model",
                        name="token.delta",
                        timestamp=datetime(2026, 1, 1, 0, 0, 1, 500000, tzinfo=UTC),
                        attributes={"delta": "hi"},
                    )
                ],
            )
        ],
    )


def _run_row() -> dict[str, Any]:
    return {
        "org_id": "123e4567-e89b-12d3-a456-426614174111",
        "project_id": "123e4567-e89b-12d3-a456-426614174000",
        "environment_id": "123e4567-e89b-12d3-a456-426614174222",
        "run_id": "run_123",
        "schema_version": CURRENT_SCHEMA_VERSION,
        "runtime": "pytest",
        "status": "succeeded",
        "started_at": datetime(2026, 1, 1, tzinfo=UTC),
        "ended_at": datetime(2026, 1, 1, 0, 0, 3, tzinfo=UTC),
        "duration_ms": 3000,
        "input_tokens": 10,
        "output_tokens": 20,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": 30,
        "cost_usd": Decimal("0.020000000"),
        "tenant_id": "tenant_123",
        "user_id": "user_123",
        "workflow_name": "workflow",
        "metadata_json": json.dumps({"org_id": "123e4567-e89b-12d3-a456-426614174111"}),
    }


def _span_row(run_id: str = "run_123") -> dict[str, Any]:
    return {
        "run_id": run_id,
        "span_id": "span_model",
        "parent_span_id": None,
        "kind": "model_call",
        "name": "call model",
        "started_at": datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        "ended_at": datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
        "input_tokens": 10,
        "output_tokens": 20,
        "cached_input_tokens": 3,
        "reasoning_tokens": 4,
        "total_tokens": 30,
        "cost_usd": Decimal("0.010000000"),
        "input_json": json.dumps({"prompt": "hello"}),
        "output_json": json.dumps({"text": "world"}),
        "attributes_json": json.dumps({"provider": "openai", "model": "gpt-5.4"}),
    }


def _event_row(run_id: str = "run_123") -> dict[str, Any]:
    return {
        "run_id": run_id,
        "span_id": "span_model",
        "event_id": "evt_token",
        "name": "token.delta",
        "timestamp": datetime(2026, 1, 1, 0, 0, 1, 500000, tzinfo=UTC),
        "attributes_json": json.dumps({"delta": "hi"}),
    }
