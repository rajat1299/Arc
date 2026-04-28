"""LangGraph invoke wrappers for OpsCanvas tracing."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterable, Iterable, Mapping, Sequence
from typing import Protocol

from opscanvas_langgraph.callbacks import merge_opscanvas_callbacks
from opscanvas_langgraph.config import OpsCanvasConfig
from opscanvas_langgraph.exporter import OpsCanvasExporter
from opscanvas_langgraph.recorder import LangGraphRunRecorder

DEFAULT_INVOKE_STREAM_MODES = ("tasks", "checkpoints", "messages", "values")


class _SyncStreamGraph(Protocol):
    def stream(
        self,
        input: object,
        *,
        config: Mapping[str, object] | None,
        version: str,
        stream_mode: Sequence[str],
    ) -> Iterable[object]: ...


class _AsyncStreamGraph(Protocol):
    def astream(
        self,
        input: object,
        *,
        config: Mapping[str, object] | None,
        version: str,
        stream_mode: Sequence[str],
    ) -> AsyncIterable[object]: ...


def traced_invoke(
    graph: _SyncStreamGraph,
    input: object,
    *,
    config: Mapping[str, object] | None = None,
    exporter: OpsCanvasExporter | None = None,
    opscanvas_config: OpsCanvasConfig | None = None,
    run_id: str | None = None,
    workflow_name: str | None = None,
    stream_modes: Sequence[str] | None = None,
) -> object:
    """Invoke a LangGraph through public streaming APIs and record one OpsCanvas run."""
    modes = _effective_stream_modes(stream_modes)
    recorder = _build_recorder(
        graph,
        exporter=exporter,
        opscanvas_config=opscanvas_config,
        run_id=run_id,
        workflow_name=workflow_name,
        stream_modes=modes,
    )
    output = _FinalOutput()
    stream: Iterable[object] | None = None

    try:
        merged_config = merge_opscanvas_callbacks(config, recorder)
        stream = graph.stream(input, config=merged_config, version="v2", stream_mode=modes)
        for chunk in stream:
            recorder.record_stream_chunk(chunk)
            output.record(chunk)
    except (GeneratorExit, KeyboardInterrupt) as exc:
        recorder.interrupt("generator_close" if isinstance(exc, GeneratorExit) else "interrupted")
        recorder.finish()
        _close_sync_stream(stream)
        raise
    except BaseException as exc:
        recorder.fail(exc)
        recorder.finish()
        _close_sync_stream(stream)
        raise
    else:
        recorder.finish()
        return output.value


async def traced_ainvoke(
    graph: _AsyncStreamGraph,
    input: object,
    *,
    config: Mapping[str, object] | None = None,
    exporter: OpsCanvasExporter | None = None,
    opscanvas_config: OpsCanvasConfig | None = None,
    run_id: str | None = None,
    workflow_name: str | None = None,
    stream_modes: Sequence[str] | None = None,
) -> object:
    """Async invoke a LangGraph through public streaming APIs and record one OpsCanvas run."""
    modes = _effective_stream_modes(stream_modes)
    recorder = _build_recorder(
        graph,
        exporter=exporter,
        opscanvas_config=opscanvas_config,
        run_id=run_id,
        workflow_name=workflow_name,
        stream_modes=modes,
    )
    output = _FinalOutput()
    stream: AsyncIterable[object] | None = None

    try:
        merged_config = merge_opscanvas_callbacks(config, recorder)
        stream = await _call_astream(graph, input, config=merged_config, stream_modes=modes)
        async for chunk in stream:
            recorder.record_stream_chunk(chunk)
            output.record(chunk)
    except (asyncio.CancelledError, GeneratorExit) as exc:
        reason = "cancelled" if isinstance(exc, asyncio.CancelledError) else "generator_close"
        recorder.interrupt(reason)
        recorder.finish()
        await _close_async_stream(stream)
        raise
    except BaseException as exc:
        recorder.fail(exc)
        recorder.finish()
        await _close_async_stream(stream)
        raise
    else:
        recorder.finish()
        return output.value


def _build_recorder(
    graph: object,
    *,
    exporter: OpsCanvasExporter | None,
    opscanvas_config: OpsCanvasConfig | None,
    run_id: str | None,
    workflow_name: str | None,
    stream_modes: Sequence[str],
) -> LangGraphRunRecorder:
    return LangGraphRunRecorder(
        exporter=exporter,
        config=opscanvas_config,
        run_id=run_id,
        workflow_name=_workflow_name(graph, workflow_name),
        stream_modes=tuple(stream_modes),
    )


def _workflow_name(graph: object, explicit: str | None) -> str:
    if explicit is not None:
        return explicit
    graph_name = getattr(graph, "name", None)
    if graph_name is not None:
        return str(graph_name)
    return "LangGraph"


def _effective_stream_modes(stream_modes: Sequence[str] | None) -> list[str]:
    return list(stream_modes or DEFAULT_INVOKE_STREAM_MODES)


async def _call_astream(
    graph: _AsyncStreamGraph,
    input: object,
    *,
    config: Mapping[str, object] | None,
    stream_modes: Sequence[str],
) -> AsyncIterable[object]:
    result = graph.astream(input, config=config, version="v2", stream_mode=stream_modes)
    if inspect.isawaitable(result):
        result = await result
    return result


def _close_sync_stream(stream: Iterable[object] | None) -> None:
    if stream is None:
        return
    close = getattr(stream, "close", None)
    if callable(close):
        close()


async def _close_async_stream(stream: AsyncIterable[object] | None) -> None:
    if stream is None:
        return
    aclose = getattr(stream, "aclose", None)
    if callable(aclose):
        result = aclose()
        if inspect.isawaitable(result):
            await result


class _FinalOutput:
    def __init__(self) -> None:
        self.value: object = None
        self._saw_values = False

    def record(self, chunk: object) -> None:
        mode, payload = _stream_mode_and_payload(chunk)
        if mode == "values":
            self.value = payload
            self._saw_values = True
            return
        if self._saw_values or mode == "tasks":
            return
        self.value = payload


def _stream_mode_and_payload(chunk: object) -> tuple[str | None, object]:
    if isinstance(chunk, dict):
        mode = chunk.get("type")
        if isinstance(mode, str):
            return mode, chunk.get("data")
        return None, chunk

    if not isinstance(chunk, tuple):
        return None, chunk
    if len(chunk) == 2 and isinstance(chunk[0], str):
        return chunk[0], chunk[1]
    if len(chunk) == 3 and isinstance(chunk[1], str):
        return chunk[1], chunk[2]
    return None, chunk
