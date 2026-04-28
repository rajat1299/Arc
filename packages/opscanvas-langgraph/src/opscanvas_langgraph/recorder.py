"""Duck-typed LangGraph stream recorder."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from hashlib import sha256
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

from opscanvas_langgraph.config import OpsCanvasConfig
from opscanvas_langgraph.exporter import OpsCanvasExporter

RUNTIME = "langgraph"
_DEFAULT_STREAM_MODES = ("tasks", "checkpoints", "messages", "values")
_ROOT_EVENT_MODES = {"custom", "updates", "values", "debug"}


class LangGraphRunRecorder:
    """Map public LangGraph stream chunks into a canonical run."""

    def __init__(
        self,
        exporter: OpsCanvasExporter | None = None,
        config: OpsCanvasConfig | None = None,
        *,
        run_id: str | None = None,
        workflow_name: str | None = None,
        thread_id: str | None = None,
        started_at: datetime | None = None,
        stream_modes: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.config = config or (
            exporter.config if exporter is not None else OpsCanvasConfig.from_env()
        )
        self.exporter = exporter or OpsCanvasExporter(config=self.config)
        self.run_id = run_id or generate_run_id()
        self.workflow_name = workflow_name
        self.thread_id = thread_id
        self.started_at = started_at or datetime.now(UTC)
        self.stream_modes = tuple(stream_modes or _DEFAULT_STREAM_MODES)

        root_attributes: dict[str, JsonValue] = {
            "runtime": RUNTIME,
            "langgraph.stream_modes": list(self.stream_modes),
        }
        _set_if_present(root_attributes, "langgraph.thread_id", thread_id)

        self._root_span = Span(
            id=f"{self.run_id}_root",
            run_id=self.run_id,
            kind=SpanKind.agent,
            name=workflow_name or "LangGraph",
            started_at=self.started_at,
            attributes=root_attributes,
        )
        self._spans: list[Span] = [self._root_span]
        self._open_task_spans: dict[str, Span] = {}
        self._task_sequence = 0
        self._metadata: dict[str, JsonValue] = {"runtime": RUNTIME}
        _set_if_present(self._metadata, "langgraph.thread_id", thread_id)
        self._usage: Usage | None = None
        self._status = RunStatus.succeeded
        self._finished_run: Run | None = None

    def record_stream_chunk(self, chunk: object) -> None:
        """Record a public LangGraph stream chunk without importing LangGraph."""
        parsed = _parse_stream_chunk(chunk)
        if parsed is None:
            self._add_event(
                self._root_span,
                "langgraph.stream",
                {"shape": _shape_name(chunk), "payload": _json_summary(chunk)},
            )
            return

        namespace, mode, payload = parsed
        attributes = _base_stream_attributes(namespace, mode)
        if mode == "tasks":
            self._record_task_payload(payload, attributes)
            return
        if mode == "checkpoints":
            attributes.update(_checkpoint_attributes(payload))
            self._add_event(self._root_span, "langgraph.checkpoint", attributes)
            return
        if mode == "messages":
            attributes.update(_message_event_attributes(payload))
            self._add_event(self._root_span, "langgraph.message", attributes)
            self._aggregate_usage(_usage_from_message_payload(payload))
            return
        if mode in _ROOT_EVENT_MODES:
            attributes["payload"] = _json_summary(payload)
            self._add_event(self._root_span, f"langgraph.{mode}", attributes)
            return

        attributes["payload"] = _json_summary(payload)
        self._add_event(self._root_span, "langgraph.stream", attributes)

    def record_interrupt(self, event: object) -> None:
        """Record a public GraphInterruptEvent-looking object."""
        attributes = _event_object_attributes(event)
        self._add_event(self._root_span, "langgraph.interrupt", attributes)
        self._metadata["langgraph.interrupt"] = _json_summary(event)
        self._mark_interrupted()

    def record_resume(self, event: object) -> None:
        """Record a public GraphResumeEvent-looking object."""
        attributes = _event_object_attributes(event)
        self._add_event(self._root_span, "langgraph.resume", attributes)
        self._metadata["langgraph.resume"] = _json_summary(event)

    def fail(self, exc: BaseException) -> None:
        """Mark the run failed and store safe exception metadata."""
        self._status = RunStatus.failed
        self._metadata["langgraph.error"] = _exception_summary(exc)
        self._add_event(
            self._root_span,
            "langgraph.error",
            {"error": _exception_summary(exc)},
        )

    def interrupt(self, reason: object) -> None:
        """Mark the run interrupted unless it has already failed."""
        self._metadata["langgraph.interrupt_reason"] = _json_summary(reason)
        self._add_event(
            self._root_span,
            "langgraph.interrupt",
            {"reason": _json_summary(reason)},
        )
        self._mark_interrupted()

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

    def _record_task_payload(
        self,
        payload: object,
        stream_attributes: dict[str, JsonValue],
    ) -> None:
        if not isinstance(payload, dict):
            attributes = dict(stream_attributes)
            attributes["payload"] = _json_summary(payload)
            self._add_event(self._root_span, "langgraph.tasks", attributes)
            return

        if _is_task_result_payload(payload):
            self._close_task_span(payload, stream_attributes)
            return

        self._open_task_span(payload, stream_attributes)

    def _open_task_span(
        self,
        payload: dict[object, object],
        stream_attributes: dict[str, JsonValue],
    ) -> None:
        task_key, span_id = self._task_key_and_span_id(payload.get("id"))
        attributes = dict(stream_attributes)
        attributes["runtime"] = RUNTIME
        _set_if_present(attributes, "langgraph.task_id", payload.get("id"))
        _set_if_present(attributes, "langgraph.triggers", payload.get("triggers"))

        span = Span(
            id=span_id,
            run_id=self.run_id,
            kind=SpanKind.custom,
            name=_optional_string(payload.get("name")) or "langgraph task",
            parent_id=self._root_span.id,
            started_at=datetime.now(UTC),
            input=_json_summary(payload.get("input")),
            attributes=attributes,
        )
        self._spans.append(span)
        self._open_task_spans[task_key] = span

    def _close_task_span(
        self,
        payload: dict[object, object],
        stream_attributes: dict[str, JsonValue],
    ) -> None:
        task_key, span_id = self._task_result_key_and_span_id(payload.get("id"))
        span = self._open_task_spans.pop(task_key, None)
        if span is None:
            span = Span(
                id=span_id,
                run_id=self.run_id,
                kind=SpanKind.custom,
                name=_optional_string(payload.get("name")) or "langgraph task",
                parent_id=self._root_span.id,
                started_at=datetime.now(UTC),
                attributes={"runtime": RUNTIME, **stream_attributes},
            )
            self._spans.append(span)

        span.name = _optional_string(payload.get("name")) or span.name
        span.ended_at = datetime.now(UTC)
        span.output_data = _json_summary(payload.get("result"))
        _set_if_present(span.attributes, "langgraph.task_id", payload.get("id"))
        _set_if_present(span.attributes, "langgraph.interrupts", payload.get("interrupts"))
        error = payload.get("error")
        interrupts = payload.get("interrupts")
        if error:
            span.attributes["langgraph.error"] = _json_summary(error)
            span.attributes["langgraph.status"] = "failed"
            self._status = RunStatus.failed
        elif _has_interrupts(interrupts):
            span.attributes["langgraph.status"] = "interrupted"
            self._mark_interrupted()
        else:
            span.attributes["langgraph.status"] = "succeeded"

    def _task_key_and_span_id(self, task_id: object) -> tuple[str, str]:
        if task_id is not None:
            task_key = str(task_id)
            digest = sha256(task_key.encode("utf-8", errors="replace")).hexdigest()[:16]
            return task_key, f"{self.run_id}_task_{digest}"

        self._task_sequence += 1
        task_key = f"local-{self._task_sequence}"
        return task_key, f"{self.run_id}_task_{self._task_sequence}"

    def _task_result_key_and_span_id(self, task_id: object) -> tuple[str, str]:
        if task_id is not None:
            return self._task_key_and_span_id(task_id)
        local_key = next(
            (key for key in self._open_task_spans if key.startswith("local-")),
            None,
        )
        if local_key is not None:
            return local_key, self._open_task_spans[local_key].id
        return self._task_key_and_span_id(task_id)

    def _aggregate_usage(self, usage: Usage | None) -> None:
        if usage is None:
            return
        if self._usage is None:
            self._usage = usage
            return

        self._usage = Usage(
            input_tokens=_sum_optional(self._usage.input_tokens, usage.input_tokens),
            output_tokens=_sum_optional(self._usage.output_tokens, usage.output_tokens),
            cached_input_tokens=_sum_optional(
                self._usage.cached_input_tokens,
                usage.cached_input_tokens,
            ),
            reasoning_tokens=_sum_optional(
                self._usage.reasoning_tokens,
                usage.reasoning_tokens,
            ),
            total_tokens=_sum_optional(self._usage.total_tokens, usage.total_tokens),
            cost_usd=_sum_optional_float(self._usage.cost_usd, usage.cost_usd),
        )

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


def _parse_stream_chunk(chunk: object) -> tuple[JsonValue | None, str, object] | None:
    if isinstance(chunk, dict):
        mode = chunk.get("type")
        if isinstance(mode, str):
            return _json_value(chunk.get("ns")), mode, chunk.get("data")
        return None

    if not isinstance(chunk, tuple):
        return None
    if len(chunk) == 2 and isinstance(chunk[0], str):
        return None, chunk[0], chunk[1]
    if len(chunk) == 3 and isinstance(chunk[1], str):
        return _json_value(chunk[0]), chunk[1], chunk[2]
    return None


def _base_stream_attributes(namespace: JsonValue | None, mode: str) -> dict[str, JsonValue]:
    attributes: dict[str, JsonValue] = {"langgraph.stream_mode": mode}
    if namespace is not None:
        attributes["langgraph.namespace"] = namespace
    return attributes


def _is_task_result_payload(payload: dict[object, object]) -> bool:
    return any(key in payload for key in ("result", "error", "interrupts"))


def _checkpoint_attributes(payload: object) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        return {"payload": _json_summary(payload)}

    attributes: dict[str, JsonValue] = {}
    for source, target in {
        "config": "config",
        "metadata": "metadata",
        "values": "values",
        "next": "next",
        "parent_config": "parent_config",
        "tasks": "tasks",
    }.items():
        if source in payload:
            attributes[f"langgraph.checkpoint.{target}"] = _json_summary(payload[source])
    return attributes


def _message_event_attributes(payload: object) -> dict[str, JsonValue]:
    message, metadata = _message_and_metadata(payload)
    attributes: dict[str, JsonValue] = {
        "message": _json_summary(message),
        "message_type": _shape_name(message),
    }
    if metadata is not None:
        attributes["metadata"] = _json_value(metadata)
    return attributes


def _message_and_metadata(payload: object) -> tuple[object, object | None]:
    if isinstance(payload, tuple) and len(payload) == 2:
        return payload[0], payload[1]
    return payload, None


def _usage_from_message_payload(payload: object) -> Usage | None:
    message, _metadata = _message_and_metadata(payload)
    usage = _usage_from(_get(message, "usage_metadata", None))
    if usage is not None:
        return usage

    response_metadata = _get(message, "response_metadata", None)
    token_usage = _get(response_metadata, "token_usage", None)
    return _usage_from(token_usage)


def _event_object_attributes(event: object) -> dict[str, JsonValue]:
    attributes: dict[str, JsonValue] = {"event_type": type(event).__name__}
    for name in ("run_id", "status", "checkpoint_id", "checkpoint_ns"):
        value = _get(event, name, None)
        if value is not None:
            attributes[name] = _json_value(value)

    for name in ("reason", "value", "interrupts", "resumable", "ns", "namespace", "when", "config"):
        value = _get(event, name, None)
        if value is not None:
            attributes[name] = _json_summary(value)
    return attributes


def _get(source: object, name: str, default: object = None) -> object:
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _set_if_present(target: dict[str, JsonValue], name: str, value: object) -> None:
    if value is not None:
        target[name] = _json_value(value)


def _usage_from(value: object) -> Usage | None:
    if value is None:
        return None

    usage = Usage(
        input_tokens=_optional_int(
            _first_present(value, "input_tokens", "prompt_tokens", "input_token_count")
        ),
        output_tokens=_optional_int(
            _first_present(value, "output_tokens", "completion_tokens", "output_token_count")
        ),
        cached_input_tokens=_optional_int(
            _first_present(
                value,
                "cached_input_tokens",
                "cache_read_input_tokens",
                ("input_token_details", "cache_read"),
                ("prompt_tokens_details", "cached_tokens"),
            )
        ),
        reasoning_tokens=_optional_int(
            _first_present(
                value,
                "reasoning_tokens",
                "thinking_tokens",
                ("output_token_details", "reasoning"),
                ("completion_tokens_details", "reasoning_tokens"),
            )
        ),
        total_tokens=_optional_int(_first_present(value, "total_tokens")),
    )
    if usage.model_dump(exclude_none=True):
        return usage
    return None


def _first_present(source: object, *names: str | tuple[str, ...]) -> object:
    for name in names:
        value = _get_path(source, name) if isinstance(name, tuple) else _get(source, name, None)
        if value is not None:
            return value
    return None


def _get_path(source: object, path: tuple[str, ...]) -> object:
    current = source
    for name in path:
        current = _get(current, name, None)
        if current is None:
            return None
    return current


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _sum_optional(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return left + right


def _sum_optional_float(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return left + right


def _has_interrupts(value: object) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, list | tuple | dict | set):
        return bool(value)
    return True


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
        item_types = [type(item).__name__ for item in value]
        if item_types:
            summary["item_types"] = cast(JsonValue, item_types)
        return summary
    if isinstance(value, dict):
        return {"type": "dict", "key_count": len(value)}
    if is_dataclass(value) and not isinstance(value, type):
        return {"type": type(value).__name__, "field_count": len(fields(value))}
    return _type_summary(value)


def _exception_summary(exc: BaseException) -> dict[str, JsonValue]:
    return {"type": type(exc).__name__, "has_error": True}


def _shape_name(value: object) -> str:
    if value is None:
        return "NoneType"
    return type(value).__name__


def _type_summary(value: object) -> dict[str, JsonValue]:
    return {"type": type(value).__name__}
