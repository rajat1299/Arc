"""Duck-typed OpenAI Agents tracing processor for OpsCanvas."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from opscanvas_core import Run, RunStatus, Span, SpanKind, generate_run_id, generate_span_id
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
        self._trace_buffers: dict[str, list[Span]] = {}
        self._active_trace_ids: list[str] = []

    def on_trace_start(self, trace: object) -> None:
        """Initialize a span buffer for a trace lifecycle."""
        trace_id = _trace_id(trace)
        if trace_id is None:
            return

        self._trace_buffers.setdefault(trace_id, [])
        self._active_trace_ids.append(trace_id)

    def on_trace_end(self, trace: object) -> None:
        """Build and export a completed run from buffered trace spans."""
        trace_id = _trace_id(trace)
        buffered_spans = None
        if trace_id is not None:
            buffered_spans = self._trace_buffers.pop(trace_id, None)
            self._forget_active_trace(trace_id)

        spans = buffered_spans if buffered_spans is not None else self.exporter.spans
        self.exporter.export_run(build_run_from_trace(trace, spans, self.exporter.config))

    def on_span_start(self, span: object) -> None:
        """Accept span lifecycle callbacks for SDK compatibility."""

    def on_span_end(self, span: object) -> None:
        """Map a completed runtime span to the canonical OpsCanvas span contract."""
        mapped_span = map_agents_span(span, self.exporter.config)
        trace_id = _span_trace_id(span) or self._single_active_trace_id()
        if trace_id is not None and trace_id in self._trace_buffers:
            if mapped_span.run_id != trace_id:
                mapped_span = mapped_span.model_copy(update={"run_id": trace_id})
            self._trace_buffers[trace_id].append(mapped_span)

        self.exporter.export([mapped_span])

    def force_flush(self) -> None:
        return self.exporter.force_flush()

    def shutdown(self) -> None:
        self.exporter.shutdown()

    def _single_active_trace_id(self) -> str | None:
        if len(self._active_trace_ids) == 1:
            return self._active_trace_ids[-1]
        return None

    def _forget_active_trace(self, trace_id: str) -> None:
        for index in range(len(self._active_trace_ids) - 1, -1, -1):
            if self._active_trace_ids[index] == trace_id:
                del self._active_trace_ids[index]
                return


def map_agents_span(span: object, config: OpsCanvasConfig | None = None) -> Span:
    """Map a duck-typed OpenAI Agents span into the OpsCanvas core span model."""
    effective_config = config or OpsCanvasConfig.from_env()
    span_data = _get(span, "span_data", None)
    attributes = _attributes_for(effective_config, span_data)
    error = _span_error(span)
    if error is not None:
        attributes["error"] = _json_value(error)

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


def build_run_from_trace(
    trace: object,
    spans: Iterable[Span],
    config: OpsCanvasConfig | None = None,
) -> Run:
    """Build a conservative OpsCanvas run from a runtime trace and mapped spans.

    This skeleton treats completed traces as succeeded unless public-looking
    trace/span attributes clearly indicate failure.
    """
    effective_config = config or OpsCanvasConfig.from_env()
    span_list = list(spans)
    trace_id = _optional_string(_first_present(trace, ("trace_id", "id", "run_id")))
    run_id = trace_id or (span_list[0].run_id if span_list else generate_run_id())
    run_spans = [span for span in span_list if span.run_id == run_id]

    return Run(
        id=run_id,
        status=_run_status(trace, run_spans),
        started_at=_run_started_at(trace, run_spans),
        ended_at=_run_ended_at(trace, run_spans),
        runtime="openai-agents",
        project_id=effective_config.project_id,
        environment=effective_config.environment,
        workflow_name=_optional_string(_first_present(trace, ("name", "workflow_name"))),
        spans=run_spans,
        metadata=_run_metadata(trace),
    )


def _trace_id(trace: object) -> str | None:
    return _optional_string(_first_present(trace, ("trace_id", "id", "run_id")))


def _span_trace_id(span: object) -> str | None:
    return _optional_string(_first_present(span, ("trace_id", "run_id")))


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


def _span_error(span: object) -> object:
    error = _get(span, "error", None)
    if error is not None:
        return error

    exported = _call_public_export(span)
    if isinstance(exported, dict):
        return exported.get("error")
    return None


def _call_public_export(span: object) -> object:
    export = _get(span, "export", None)
    if not callable(export):
        return None

    try:
        return export()
    except Exception:
        return None


def _run_status(trace: object, spans: Iterable[Span]) -> RunStatus:
    status = _optional_string(_first_present(trace, ("status", "state", "outcome")))
    if status is not None and status.lower() in {"failed", "failure", "error"}:
        return RunStatus.failed
    if _first_present(trace, ("error", "exception")) is not None:
        return RunStatus.failed

    for span in spans:
        span_status = span.attributes.get("status")
        if isinstance(span_status, str) and span_status.lower() in {"failed", "failure", "error"}:
            return RunStatus.failed
        if "error" in span.attributes or "exception" in span.attributes:
            return RunStatus.failed

    return RunStatus.succeeded


def _run_started_at(trace: object, spans: list[Span]) -> datetime:
    explicit_started_at = _optional_datetime(_first_present(trace, ("started_at", "start_time")))
    if explicit_started_at is not None:
        return explicit_started_at
    if spans:
        return min(span.started_at for span in spans)
    return datetime.now(UTC)


def _run_ended_at(trace: object, spans: list[Span]) -> datetime | None:
    explicit_ended_at = _optional_datetime(_first_present(trace, ("ended_at", "end_time")))
    if explicit_ended_at is not None:
        return explicit_ended_at

    ended_at_values = [span.ended_at for span in spans if span.ended_at is not None]
    if ended_at_values:
        return max(ended_at_values)
    return None


def _run_metadata(trace: object) -> dict[str, JsonValue]:
    metadata: dict[str, JsonValue] = {
        "runtime": "openai-agents",
    }
    group_id = _optional_string(_first_present(trace, ("group_id", "trace_group_id")))
    if group_id is not None:
        metadata["group_id"] = group_id
    return metadata


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
