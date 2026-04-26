"""Duck-typed OpenAI Agents tracing processor for OpsCanvas."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from opscanvas_core import Span, SpanKind, generate_run_id, generate_span_id
from pydantic import JsonValue

from opscanvas_agents.config import OpsCanvasConfig
from opscanvas_agents.exporter import OpsCanvasExporter


class OpsCanvasProcessor:
    """Tracing processor compatible with OpenAI Agents public processor hooks."""

    def __init__(
        self,
        exporter: OpsCanvasExporter | None = None,
        config: OpsCanvasConfig | None = None,
    ) -> None:
        self.exporter = exporter or OpsCanvasExporter(config=config)

    def on_trace_start(self, trace: object) -> None:
        """Accept trace lifecycle callbacks for SDK compatibility."""

    def on_trace_end(self, trace: object) -> None:
        """Accept trace lifecycle callbacks for SDK compatibility."""

    def on_span_start(self, span: object) -> None:
        """Accept span lifecycle callbacks for SDK compatibility."""

    def on_span_end(self, span: object) -> None:
        """Map a completed runtime span to the canonical OpsCanvas span contract."""
        self.exporter.export([map_agents_span(span, self.exporter.config)])

    def force_flush(self) -> None:
        return self.exporter.force_flush()

    def shutdown(self) -> None:
        self.exporter.shutdown()


def map_agents_span(span: object, config: OpsCanvasConfig | None = None) -> Span:
    """Map a duck-typed OpenAI Agents span into the OpsCanvas core span model."""
    effective_config = config or OpsCanvasConfig.from_env()
    span_data = _get(span, "span_data", None)
    attributes = _attributes_for(effective_config, span_data)

    return Span(
        id=_string_or_generated(_first_present(span, ("span_id", "id")), generate_span_id),
        run_id=_string_or_generated(_first_present(span, ("trace_id", "run_id")), generate_run_id),
        kind=_span_kind(span_data),
        name=_span_name(span_data),
        parent_id=_optional_string(_first_present(span, ("parent_id", "parent_span_id"))),
        started_at=_datetime_or_now(_first_present(span, ("started_at", "start_time"))),
        ended_at=_optional_datetime(_first_present(span, ("ended_at", "end_time"))),
        input=_json_value(_get(span_data, "input", None)),
        output=_json_value(_get(span_data, "output", None)),
        attributes=attributes,
    )


def _span_kind(span_data: object) -> SpanKind:
    data_type = _data_type(span_data)
    kind_by_type = {
        "agent": SpanKind.agent,
        "generation": SpanKind.model_call,
        "model": SpanKind.model_call,
        "model_call": SpanKind.model_call,
        "response": SpanKind.model_call,
        "function": SpanKind.tool_call,
        "tool": SpanKind.tool_call,
        "tool_call": SpanKind.tool_call,
        "handoff": SpanKind.handoff,
        "guardrail": SpanKind.guardrail,
        "mcp_list": SpanKind.mcp_list,
        "mcp_list_tools": SpanKind.mcp_list,
        "sandbox": SpanKind.sandbox_op,
        "sandbox_op": SpanKind.sandbox_op,
        "retry": SpanKind.retry,
    }
    return kind_by_type.get(data_type, SpanKind.custom)


def _span_name(span_data: object) -> str:
    for field_name in ("name", "tool_name", "model", "agent_name", "function_name"):
        value = _get(span_data, field_name, None)
        if isinstance(value, str) and value:
            return value

    data_type = _data_type(span_data)
    return data_type if data_type else "openai_agents.span"


def _attributes_for(config: OpsCanvasConfig, span_data: object) -> dict[str, JsonValue]:
    attributes: dict[str, JsonValue] = {
        "runtime": "openai-agents",
    }
    if config.project_id is not None:
        attributes["project_id"] = config.project_id
    if config.environment is not None:
        attributes["environment"] = config.environment

    data_type = _data_type(span_data)
    if data_type:
        attributes["agents_span_type"] = data_type
    model = _get(span_data, "model", None)
    if isinstance(model, str) and model:
        attributes["model"] = model

    return attributes


def _data_type(span_data: object) -> str:
    explicit_type = _get(span_data, "type", None)
    if isinstance(explicit_type, str):
        return explicit_type.lower()

    return type(span_data).__name__.removesuffix("SpanData").lower()


def _first_present(source: object, names: tuple[str, ...]) -> object:
    for name in names:
        value = _get(source, name, None)
        if value is not None:
            return value
    return None


def _get(source: object, name: str, default: object) -> object:
    return getattr(source, name, default)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _string_or_generated(value: object, generator: Callable[[], str]) -> str:
    if value is not None:
        return str(value)
    return generator()


def _datetime_or_now(value: object) -> datetime:
    parsed = _optional_datetime(value)
    return parsed if parsed is not None else datetime.now(UTC)


def _optional_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)
