"""Pure ClickHouse row mappers for canonical OpsCanvas contracts."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import JsonValue

if TYPE_CHECKING:
    from opscanvas_core.events import Run, Span, Usage

ClickHouseRow = dict[str, Any]


def run_to_clickhouse_row(run: Run) -> ClickHouseRow:
    """Convert a canonical run into a row for the ClickHouse ``runs`` table."""
    ids = _hierarchy_ids(run)
    usage = _usage_columns(run.usage)
    return {
        **ids,
        "environment": run.environment,
        "run_id": run.id,
        "schema_version": run.schema_version,
        "runtime": run.runtime,
        "status": run.status.value,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "duration_ms": _duration_ms(run.started_at, run.ended_at),
        **usage,
        "audio_input_tokens": None,
        "audio_output_tokens": None,
        "batch_discount_multiplier": None,
        "tenant_id": run.tenant_id,
        "user_id": run.user_id,
        "workflow_name": run.workflow_name,
        "metadata_json": _json_dumps(run.metadata),
        "runtime_attributes_json": _json_dumps({}),
    }


def spans_to_clickhouse_rows(run: Run) -> list[ClickHouseRow]:
    """Convert every span on a canonical run into ClickHouse ``spans`` rows."""
    ids = _hierarchy_ids(run)
    return [_span_to_clickhouse_row(run, span, ids) for span in run.spans]


def span_events_to_clickhouse_rows(run: Run) -> list[ClickHouseRow]:
    """Convert every span event on a canonical run into ``span_events`` rows."""
    ids = _hierarchy_ids(run)
    return [
        {
            **ids,
            "run_id": run.id,
            "span_id": event.span_id,
            "event_id": event.id,
            "name": event.name,
            "timestamp": event.timestamp,
            "attributes_json": _json_dumps(event.attributes),
        }
        for span in run.spans
        for event in span.events
    ]


def _span_to_clickhouse_row(run: Run, span: Span, ids: ClickHouseRow) -> ClickHouseRow:
    dumped = span.model_dump(mode="json", by_alias=True)
    usage = _usage_columns(span.usage)
    return {
        **ids,
        "run_id": span.run_id,
        "span_id": span.id,
        "parent_span_id": span.parent_id,
        "kind": span.kind.value,
        "name": span.name,
        "started_at": span.started_at,
        "ended_at": span.ended_at,
        "duration_ms": _duration_ms(span.started_at, span.ended_at),
        **usage,
        "audio_input_tokens": None,
        "audio_output_tokens": None,
        "batch_discount_multiplier": None,
        "input_json": _json_dumps(dumped["input"]),
        "output_json": _json_dumps(dumped["output"]),
        "attributes_json": _json_dumps(span.attributes),
        "runtime": run.runtime,
        "provider": _string_attribute(span.attributes, "provider"),
        "model": _model_name(span.attributes),
        "tool_name": _tool_name(span),
        "service_tier": _service_tier(span.attributes),
    }


def _usage_columns(usage: Usage | None) -> ClickHouseRow:
    return {
        "input_tokens": usage.input_tokens if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
        "cached_input_tokens": usage.cached_input_tokens if usage else None,
        "reasoning_tokens": usage.reasoning_tokens if usage else None,
        "total_tokens": usage.total_tokens if usage else None,
        "cost_usd": usage.cost_usd if usage else None,
    }


def _duration_ms(started_at: datetime, ended_at: datetime | None) -> int | None:
    if ended_at is None or ended_at < started_at:
        return None
    return int((ended_at - started_at).total_seconds() * 1000)


def _hierarchy_ids(run: Run) -> ClickHouseRow:
    return {
        "org_id": _valid_uuid(_metadata_string(run.metadata, "org_id")),
        "project_id": _valid_uuid(run.project_id),
        "environment_id": _valid_uuid(run.environment),
    }


def _metadata_string(metadata: dict[str, JsonValue], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) else None


def _valid_uuid(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _model_name(attributes: dict[str, JsonValue]) -> str | None:
    return _string_attribute(attributes, "model") or _string_attribute(attributes, "agent.model")


def _tool_name(span: Span) -> str | None:
    return (
        _string_attribute(span.attributes, "tool")
        or _string_attribute(span.attributes, "tool.name")
        or (span.name if span.kind.value == "tool_call" else None)
    )


def _service_tier(attributes: dict[str, JsonValue]) -> str | None:
    return _string_attribute(attributes, "service_tier") or _string_attribute(
        attributes, "service.tier"
    )


def _string_attribute(attributes: dict[str, JsonValue], key: str) -> str | None:
    value = attributes.get(key)
    return value if isinstance(value, str) else None


def _json_dumps(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
