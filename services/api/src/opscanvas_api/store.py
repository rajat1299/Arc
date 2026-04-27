from __future__ import annotations

import builtins
import json
from collections.abc import Mapping
from decimal import Decimal
from threading import RLock
from typing import Any, Protocol, SupportsFloat, SupportsInt, cast

from opscanvas_core.events import Run, RunStatus, Span, SpanEvent, Usage
from pydantic import JsonValue

from opscanvas_api.storage import (
    run_to_clickhouse_row,
    span_events_to_clickhouse_rows,
    spans_to_clickhouse_rows,
)

RUN_COLUMNS = [
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
SPAN_COLUMNS = [
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
SPAN_EVENT_COLUMNS = [
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

ClickHouseRow = dict[str, Any]


class RunStore(Protocol):
    def upsert(self, run: Run) -> None:
        """Store a canonical run, replacing any previous run with the same ID."""

    def get(self, run_id: str) -> Run | None:
        """Return a canonical run by ID."""

    def list(
        self,
        *,
        status: RunStatus | None = None,
        runtime: str | None = None,
        tenant_id: str | None = None,
        environment: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Run]:
        """Return canonical runs sorted by newest start time first."""


class InMemoryRunStore:
    """Process-local run store for local/dev ingestion and query loops."""

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._lock = RLock()

    def upsert(self, run: Run) -> None:
        with self._lock:
            self._runs[run.id] = run.model_copy(deep=True)

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            return run.model_copy(deep=True)

    def list(
        self,
        *,
        status: RunStatus | None = None,
        runtime: str | None = None,
        tenant_id: str | None = None,
        environment: str | None = None,
        limit: int | None = None,
    ) -> list[Run]:
        with self._lock:
            runs = list(self._runs.values())

        filtered = [
            run
            for run in runs
            if (status is None or run.status == status)
            and (runtime is None or run.runtime == runtime)
            and (tenant_id is None or run.tenant_id == tenant_id)
            and (environment is None or run.environment == environment)
        ]
        sorted_runs = sorted(filtered, key=lambda run: run.started_at, reverse=True)
        limited_runs = sorted_runs[:limit] if limit is not None else sorted_runs
        return [run.model_copy(deep=True) for run in limited_runs]


class ClickHouseRunStore:
    """ClickHouse-backed run store for local/dev persistence."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def upsert(self, run: Run) -> None:
        parameters = {"run_id": run.id}
        for table in ("span_events", "spans", "runs"):
            self._client.command(
                (
                    f"ALTER TABLE {table} DELETE WHERE run_id = {{run_id:String}} "
                    "SETTINGS mutations_sync = 1"
                ),
                parameters=parameters,
            )

        self._insert_rows("runs", [run_to_clickhouse_row(run)], RUN_COLUMNS)
        self._insert_rows("spans", spans_to_clickhouse_rows(run), SPAN_COLUMNS)
        self._insert_rows("span_events", span_events_to_clickhouse_rows(run), SPAN_EVENT_COLUMNS)

    def get(self, run_id: str) -> Run | None:
        run_rows = self._query_rows(
            f"""
            SELECT {", ".join(_read_run_columns())}
            FROM runs
            WHERE run_id = {{run_id:String}}
            ORDER BY started_at DESC
            LIMIT 1
            """,
            {"run_id": run_id},
        )
        if not run_rows:
            return None
        return self._runs_from_rows(run_rows)[0]

    def list(
        self,
        *,
        status: RunStatus | None = None,
        runtime: str | None = None,
        tenant_id: str | None = None,
        environment: str | None = None,
        limit: int | None = None,
    ) -> list[Run]:
        where_clauses: list[str] = []
        parameters: dict[str, str | int] = {}
        if status is not None:
            where_clauses.append("status = {status:String}")
            parameters["status"] = status.value
        if runtime is not None:
            where_clauses.append("runtime = {runtime:String}")
            parameters["runtime"] = runtime
        if tenant_id is not None:
            where_clauses.append("tenant_id = {tenant_id:String}")
            parameters["tenant_id"] = tenant_id
        if environment is not None:
            where_clauses.append("environment_id = {environment:String}")
            parameters["environment"] = environment

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT {limit:UInt64}"
            parameters["limit"] = limit

        run_rows = self._query_rows(
            f"""
            SELECT {", ".join(_read_run_columns())}
            FROM runs
            {where_sql}
            ORDER BY started_at DESC
            {limit_sql}
            """,
            parameters,
        )
        return self._runs_from_rows(run_rows)

    def _insert_rows(
        self,
        table: str,
        rows: builtins.list[ClickHouseRow],
        columns: builtins.list[str],
    ) -> None:
        if rows:
            data = [[row[column] for column in columns] for row in rows]
            self._client.insert(table, data, column_names=columns)

    def _runs_from_rows(
        self, run_rows: builtins.list[ClickHouseRow]
    ) -> builtins.list[Run]:
        run_ids = [str(row["run_id"]) for row in run_rows]
        if not run_ids:
            return []

        span_rows = self._query_rows(
            f"""
            SELECT {", ".join(_read_span_columns())}
            FROM spans
            WHERE run_id IN {{run_ids:Array(String)}}
            ORDER BY run_id, started_at, span_id
            """,
            {"run_ids": run_ids},
        )
        event_rows = self._query_rows(
            f"""
            SELECT {", ".join(_read_event_columns())}
            FROM span_events
            WHERE run_id IN {{run_ids:Array(String)}}
            ORDER BY run_id, span_id, timestamp, event_id
            """,
            {"run_ids": run_ids},
        )
        events_by_span_key: dict[tuple[str, str], list[SpanEvent]] = {}
        for row in event_rows:
            event = _event_from_row(row)
            key = (str(row["run_id"]), event.span_id)
            events_by_span_key.setdefault(key, []).append(event)

        spans_by_run_id: dict[str, list[Span]] = {}
        for row in span_rows:
            run_id = str(row["run_id"])
            span = _span_from_row(row, events_by_span_key.get((run_id, str(row["span_id"])), []))
            spans_by_run_id.setdefault(run_id, []).append(span)

        return [_run_from_row(row, spans_by_run_id.get(str(row["run_id"]), [])) for row in run_rows]

    def _query_rows(
        self, query: str, parameters: Mapping[str, object]
    ) -> builtins.list[ClickHouseRow]:
        result: Any = self._client.query(query, parameters=dict(parameters))
        if hasattr(result, "named_results"):
            return [dict(row) for row in result.named_results()]
        rows = result.result_rows
        return [dict(row) for row in rows]


def _read_run_columns() -> list[str]:
    return [
        "org_id",
        "project_id",
        "environment_id",
        "run_id",
        "schema_version",
        "runtime",
        "status",
        "started_at",
        "ended_at",
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "total_tokens",
        "cost_usd",
        "tenant_id",
        "user_id",
        "workflow_name",
        "metadata_json",
    ]


def _read_span_columns() -> list[str]:
    return [
        "run_id",
        "span_id",
        "parent_span_id",
        "kind",
        "name",
        "started_at",
        "ended_at",
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "total_tokens",
        "cost_usd",
        "input_json",
        "output_json",
        "attributes_json",
    ]


def _read_event_columns() -> list[str]:
    return ["run_id", "span_id", "event_id", "name", "timestamp", "attributes_json"]


def _run_from_row(row: ClickHouseRow, spans: list[Span]) -> Run:
    metadata = _json_object(row.get("metadata_json"))
    return Run.model_validate(
        {
            "id": row["run_id"],
            "schema_version": row["schema_version"],
            "status": row["status"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "runtime": row["runtime"],
            "project_id": _optional_string(row.get("project_id")),
            "environment": _optional_string(row.get("environment_id")),
            "tenant_id": row["tenant_id"],
            "user_id": row["user_id"],
            "workflow_name": row["workflow_name"],
            "usage": _usage_from_row(row),
            "metadata": metadata,
            "spans": spans,
        }
    )


def _span_from_row(row: ClickHouseRow, events: list[SpanEvent]) -> Span:
    return Span.model_validate(
        {
            "id": row["span_id"],
            "run_id": row["run_id"],
            "kind": row["kind"],
            "name": row["name"],
            "parent_id": row["parent_span_id"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "usage": _usage_from_row(row),
            "input": _json_value(row.get("input_json")),
            "output": _json_value(row.get("output_json")),
            "attributes": _json_object(row.get("attributes_json")),
            "events": events,
        }
    )


def _event_from_row(row: ClickHouseRow) -> SpanEvent:
    return SpanEvent.model_validate(
        {
            "id": row["event_id"],
            "span_id": row["span_id"],
            "name": row["name"],
            "timestamp": row["timestamp"],
            "attributes": _json_object(row.get("attributes_json")),
        }
    )


def _usage_from_row(row: ClickHouseRow) -> Usage | None:
    values = {
        "input_tokens": _optional_int(row.get("input_tokens")),
        "output_tokens": _optional_int(row.get("output_tokens")),
        "cached_input_tokens": _optional_int(row.get("cached_input_tokens")),
        "reasoning_tokens": _optional_int(row.get("reasoning_tokens")),
        "total_tokens": _optional_int(row.get("total_tokens")),
        "cost_usd": _optional_float(row.get("cost_usd")),
    }
    if all(value is None for value in values.values()):
        return None
    return Usage.model_validate(values)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int | str | Decimal):
        return int(value)
    return int(cast(SupportsInt, value))


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, int | float | str):
        return float(value)
    return float(cast(SupportsFloat, value))


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)


def _json_object(value: object) -> dict[str, JsonValue]:
    parsed = _json_value(value)
    return parsed if isinstance(parsed, dict) else {}


def _json_value(value: object) -> JsonValue:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return cast(JsonValue, json.loads(value))
    return cast(JsonValue, value)
