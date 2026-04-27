"""Duck-typed Claude Agent SDK message recorder."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from typing import cast

from opscanvas_core import (
    Run,
    RunStatus,
    Span,
    SpanEvent,
    SpanKind,
    Usage,
    generate_event_id,
    generate_run_id,
)
from pydantic import JsonValue

from opscanvas_claude.config import OpsCanvasConfig
from opscanvas_claude.exporter import OpsCanvasExporter

RUNTIME = "claude-agent-sdk"
PROVIDER = "anthropic"


class ClaudeRunRecorder:
    """Map public-looking Claude Agent SDK messages into a canonical run."""

    def __init__(
        self,
        exporter: OpsCanvasExporter | None = None,
        config: OpsCanvasConfig | None = None,
        *,
        run_id: str | None = None,
        workflow_name: str | None = None,
        started_at: datetime | None = None,
    ) -> None:
        self.config = config or (
            exporter.config if exporter is not None else OpsCanvasConfig.from_env()
        )
        self.exporter = exporter or OpsCanvasExporter(config=self.config)
        self.run_id = run_id or generate_run_id()
        self.workflow_name = workflow_name
        self.started_at = started_at or datetime.now(UTC)
        self._root_span = Span(
            id=f"{self.run_id}_root",
            run_id=self.run_id,
            kind=SpanKind.agent,
            name=workflow_name or "claude agent",
            started_at=self.started_at,
            attributes={"runtime": RUNTIME, "provider": PROVIDER},
        )
        self._spans: list[Span] = [self._root_span]
        self._metadata: dict[str, JsonValue] = {"runtime": RUNTIME, "provider": PROVIDER}
        self._usage: Usage | None = None
        self._status = RunStatus.succeeded
        self._finished_run: Run | None = None

    def record_message(self, message: object) -> None:
        """Record a duck-typed Claude SDK message object."""
        message_type = type(message).__name__
        if message_type == "UserMessage":
            self._add_event(
                self._root_span,
                "claude.user_message",
                {"content": _json_summary(_get(message, "content", None))},
            )
            return
        if message_type == "AssistantMessage":
            self._record_assistant_message(message)
            return
        if message_type == "ResultMessage":
            self._record_result_message(message)
            return
        if message_type in {
            "SystemMessage",
            "TaskStartedMessage",
            "TaskProgressMessage",
            "TaskNotificationMessage",
        }:
            self._record_system_or_task_message(message, message_type)
            return
        if message_type == "StreamEvent":
            self._add_event(self._root_span, "claude.stream_event", _message_attributes(message))
            return
        if message_type == "RateLimitEvent":
            self._add_event(self._root_span, "claude.rate_limit", _message_attributes(message))
            return

        self._add_event(
            self._root_span,
            "claude.message",
            _unknown_message_attributes(message),
        )

    def finish(self, ended_at: datetime | None = None) -> Run:
        """Return and export the completed canonical run."""
        if self._finished_run is not None:
            return self._finished_run

        finished_at = ended_at or datetime.now(UTC)
        for span in self._spans:
            if span.ended_at is None:
                span.ended_at = finished_at

        run = Run(
            id=self.run_id,
            status=self._status,
            started_at=self.started_at,
            ended_at=finished_at,
            runtime=RUNTIME,
            project_id=self.config.project_id,
            environment=self.config.environment,
            workflow_name=self.workflow_name,
            usage=self._usage,
            metadata=self._metadata,
            spans=list(self._spans),
        )
        self.exporter.export(self._spans)
        self.exporter.export_run(run)
        self._finished_run = run
        return run

    def _record_assistant_message(self, message: object) -> None:
        content = _content_blocks(_get(message, "content", []))
        model = _optional_string(_get(message, "model", None))
        error = _get(message, "error", None)
        attributes: dict[str, JsonValue] = {
            "runtime": RUNTIME,
            "provider": PROVIDER,
        }
        _set_if_present(attributes, "model", model)
        _set_if_present(attributes, "claude.message_id", _get(message, "message_id", None))
        _set_if_present(attributes, "claude.stop_reason", _get(message, "stop_reason", None))
        _set_if_present(attributes, "claude.session_id", _get(message, "session_id", None))
        _set_if_present(attributes, "claude.uuid", _get(message, "uuid", None))
        if error is not None:
            attributes["claude.error"] = _json_summary(error)
            self._mark_failed()

        span = Span(
            id=f"{self.run_id}_model_{len(self._spans)}",
            run_id=self.run_id,
            kind=SpanKind.model_call,
            name=model or "claude assistant message",
            parent_id=self._root_span.id,
            started_at=_optional_datetime(_get(message, "started_at", None)) or datetime.now(UTC),
            ended_at=_optional_datetime(_get(message, "ended_at", None)),
            usage=_usage_from(_get(message, "usage", None)),
            input=content,
            output=content,
            attributes=attributes,
        )
        for block in _iter_blocks(_get(message, "content", [])):
            block_type = type(block).__name__
            if block_type in {"ToolUseBlock", "ServerToolUseBlock"}:
                self._add_event(span, "claude.tool_use", _block_attributes(block))
            elif block_type in {"ToolResultBlock", "ServerToolResultBlock"}:
                self._add_event(span, "claude.tool_result", _block_attributes(block))
        self._spans.append(span)

    def _record_result_message(self, message: object) -> None:
        total_cost_usd = _optional_float(_get(message, "total_cost_usd", None))
        usage = _usage_from(_get(message, "usage", None), cost_usd=total_cost_usd)
        if usage is not None:
            self._usage = usage

        attributes = _message_attributes(message)
        self._add_event(self._root_span, "claude.result", attributes)
        for source_name, metadata_name in {
            "session_id": "claude.session_id",
            "stop_reason": "claude.stop_reason",
            "num_turns": "claude.num_turns",
            "duration_ms": "claude.duration_ms",
            "duration_api_ms": "claude.duration_api_ms",
            "total_cost_usd": "claude.total_cost_usd",
        }.items():
            _set_if_present(self._metadata, metadata_name, _get(message, source_name, None))
        errors = _get(message, "errors", None)
        if errors:
            self._metadata["claude.errors"] = _error_summary(errors)

        if _truthy(_get(message, "is_error", None)) or errors:
            self._mark_failed()
        elif _indicates_interrupted(_get(message, "stop_reason", None)):
            self._mark_interrupted()

    def _record_system_or_task_message(self, message: object, message_type: str) -> None:
        event_name = {
            "SystemMessage": "claude.system_message",
            "TaskStartedMessage": "claude.task_started",
            "TaskProgressMessage": "claude.task_progress",
            "TaskNotificationMessage": "claude.task_notification",
        }[message_type]
        attributes = _message_attributes(message)
        self._add_event(self._root_span, event_name, attributes)

        status = _get(message, "status", None)
        if _indicates_failed(status):
            self._mark_failed()
        elif _indicates_interrupted(status):
            self._mark_interrupted()

    def _mark_failed(self) -> None:
        self._status = RunStatus.failed

    def _mark_interrupted(self) -> None:
        if self._status is not RunStatus.failed:
            self._status = RunStatus.interrupted

    def _add_event(self, span: Span, name: str, attributes: dict[str, JsonValue]) -> None:
        span.events.append(
            SpanEvent(
                id=generate_event_id(),
                span_id=span.id,
                name=name,
                timestamp=datetime.now(UTC),
                attributes=attributes,
            )
        )


def _get(source: object, name: str, default: object = None) -> object:
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _set_if_present(target: dict[str, JsonValue], name: str, value: object) -> None:
    if value is not None:
        target[name] = _json_value(value)


def _content_blocks(value: object) -> JsonValue:
    return _json_summary(list(_iter_blocks(value)))


def _iter_blocks(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value is None:
        return []
    return [value]


def _block_attributes(block: object) -> dict[str, JsonValue]:
    attributes = _message_attributes(block)
    attributes.setdefault("block_type", type(block).__name__)
    return attributes


_MESSAGE_FIELDS: dict[str, tuple[str, ...]] = {
    "ResultMessage": (
        "total_cost_usd",
        "usage",
        "is_error",
        "errors",
        "stop_reason",
        "session_id",
        "num_turns",
        "duration_ms",
        "duration_api_ms",
    ),
    "SystemMessage": ("subtype", "data"),
    "TaskStartedMessage": (
        "task_id",
        "parent_task_id",
        "description",
        "message",
        "status",
        "metadata",
    ),
    "TaskProgressMessage": (
        "task_id",
        "message",
        "status",
        "progress",
        "current",
        "total",
        "metadata",
    ),
    "TaskNotificationMessage": ("task_id", "status", "message", "metadata"),
    "StreamEvent": ("event", "data"),
    "RateLimitEvent": (
        "message",
        "delay_seconds",
        "retry_after",
        "reset_at",
        "resets_at",
        "limit",
        "remaining",
    ),
    "ToolUseBlock": ("id", "name", "input"),
    "ToolResultBlock": ("tool_use_id", "content", "is_error"),
    "ServerToolUseBlock": ("id", "name", "input"),
    "ServerToolResultBlock": ("tool_use_id", "content", "is_error"),
    "TextBlock": ("text",),
    "ThinkingBlock": ("thinking", "text", "signature"),
}


def _message_attributes(message: object) -> dict[str, JsonValue]:
    message_type = type(message).__name__
    fields_to_record = _MESSAGE_FIELDS.get(message_type)
    if fields_to_record is None:
        return _unknown_message_attributes(message)

    attributes: dict[str, JsonValue] = {}
    for name in fields_to_record:
        value = _get(message, name, None)
        if value is not None:
            attributes[name] = _field_value(name, value)
    return attributes


_CONTENT_FIELDS = {
    "content",
    "data",
    "description",
    "error",
    "errors",
    "input",
    "message",
    "metadata",
    "signature",
    "text",
    "thinking",
}


def _field_value(name: str, value: object) -> JsonValue:
    if name == "errors":
        return _error_summary(value)
    if name in _CONTENT_FIELDS:
        return _json_summary(value)
    return _json_value(value)


def _unknown_message_attributes(message: object) -> dict[str, JsonValue]:
    return {"message_type": type(message).__name__}


def _usage_from(value: object, *, cost_usd: float | None = None) -> Usage | None:
    if value is None and cost_usd is None:
        return None

    usage = Usage(
        input_tokens=_optional_int(_first_present(value, "input_tokens", "prompt_tokens")),
        output_tokens=_optional_int(_first_present(value, "output_tokens", "completion_tokens")),
        cached_input_tokens=_optional_int(
            _first_present(value, "cached_input_tokens", "cache_read_input_tokens")
        ),
        reasoning_tokens=_optional_int(
            _first_present(value, "reasoning_tokens", "thinking_tokens")
        ),
        total_tokens=_optional_int(_first_present(value, "total_tokens")),
        cost_usd=cost_usd,
    )
    if usage.model_dump(exclude_none=True):
        return usage
    return None


def _first_present(source: object, *names: str) -> object:
    for name in names:
        value = _get(source, name, None)
        if value is not None:
            return value
    return None


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _optional_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _truthy(value: object) -> bool:
    return isinstance(value, bool) and value


def _indicates_failed(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value.lower() in {"failed", "failure", "error", "errored"}


def _indicates_interrupted(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.lower().replace("-", "_")
    return normalized in {
        "interrupted",
        "interrupt",
        "user_interrupt",
        "stopped",
        "stop",
        "aborted",
    }


def _json_value(value: object) -> JsonValue:
    return _safe_json_value(value, set())


def _safe_json_value(value: object, seen: set[int]) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    value_id = id(value)
    if value_id in seen:
        return "<cycle>"
    if isinstance(value, list):
        seen.add(value_id)
        try:
            return [_safe_json_value(item, seen) for item in value]
        finally:
            seen.remove(value_id)
    if isinstance(value, tuple):
        seen.add(value_id)
        try:
            return [_safe_json_value(item, seen) for item in value]
        finally:
            seen.remove(value_id)
    if isinstance(value, dict):
        seen.add(value_id)
        try:
            return {str(key): _safe_json_value(item, seen) for key, item in value.items()}
        finally:
            seen.remove(value_id)
    if is_dataclass(value) and not isinstance(value, type):
        return _type_summary(value)

    return _type_summary(value)


def _json_summary(value: object) -> JsonValue:
    if isinstance(value, str):
        return {"type": "str", "length": len(value)}
    if isinstance(value, bool):
        return {"type": "bool"}
    if isinstance(value, int | float):
        return {"type": type(value).__name__}
    if value is None:
        return {"type": "NoneType"}
    if isinstance(value, list | tuple):
        summary: dict[str, JsonValue] = {
            "type": "list",
            "item_count": len(value),
        }
        block_types = [type(item).__name__ for item in value]
        if block_types:
            summary["block_types"] = cast(JsonValue, block_types)
        return summary
    if isinstance(value, dict):
        return {"type": "dict", "key_count": len(value)}
    if is_dataclass(value) and not isinstance(value, type):
        return {"type": type(value).__name__, "field_count": len(fields(value))}
    return _type_summary(value)


def _error_summary(value: object) -> JsonValue:
    summary = _json_summary(value)
    if isinstance(value, list | tuple):
        assert isinstance(summary, dict)
        summary["error_count"] = len(value)
        summary.pop("block_types", None)
    elif value is not None:
        assert isinstance(summary, dict)
        summary["has_error"] = True
    return summary


def _type_summary(value: object) -> dict[str, JsonValue]:
    return {"type": type(value).__name__}
