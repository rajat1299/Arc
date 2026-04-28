"""LangGraph stream wrappers for OpsCanvas tracing."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterable, Iterable, Mapping, Sequence
from typing import Protocol

from opscanvas_langgraph.callbacks import merge_opscanvas_callbacks
from opscanvas_langgraph.config import OpsCanvasConfig
from opscanvas_langgraph.exporter import OpsCanvasExporter
from opscanvas_langgraph.invoke import (
    StreamModes,
    _build_recorder,
    _close_async_stream,
    _close_sync_stream,
    _effective_stream_modes,
)

_RESERVED_STREAM_KWARGS = frozenset({"config", "version", "stream_mode"})


class _SyncStreamGraph(Protocol):
    def stream(
        self,
        input: object,
        *,
        config: Mapping[str, object] | None,
        version: str,
        stream_mode: Sequence[str],
        **kwargs: object,
    ) -> Iterable[object]: ...


class _AsyncStreamGraph(Protocol):
    def astream(
        self,
        input: object,
        *,
        config: Mapping[str, object] | None,
        version: str,
        stream_mode: Sequence[str],
        **kwargs: object,
    ) -> AsyncIterable[object]: ...


def traced_stream(
    graph: _SyncStreamGraph,
    input: object,
    *,
    config: Mapping[str, object] | None = None,
    exporter: OpsCanvasExporter | None = None,
    opscanvas_config: OpsCanvasConfig | None = None,
    run_id: str | None = None,
    workflow_name: str | None = None,
    stream_modes: StreamModes = None,
    **kwargs: object,
) -> Iterable[object]:
    """Stream a LangGraph unchanged while recording one OpsCanvas run."""
    _raise_for_reserved_stream_kwargs(kwargs)
    modes = _effective_stream_modes(stream_modes)
    recorder = _build_recorder(
        graph,
        exporter=exporter,
        opscanvas_config=opscanvas_config,
        run_id=run_id,
        workflow_name=workflow_name,
        stream_modes=modes,
    )
    stream: Iterable[object] | None = None

    try:
        merged_config = merge_opscanvas_callbacks(config, recorder)
        stream = graph.stream(
            input,
            config=merged_config,
            version="v2",
            stream_mode=modes,
            **kwargs,
        )
        for chunk in stream:
            recorder.record_stream_chunk(chunk)
            yield chunk
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


async def traced_astream(
    graph: _AsyncStreamGraph,
    input: object,
    *,
    config: Mapping[str, object] | None = None,
    exporter: OpsCanvasExporter | None = None,
    opscanvas_config: OpsCanvasConfig | None = None,
    run_id: str | None = None,
    workflow_name: str | None = None,
    stream_modes: StreamModes = None,
    **kwargs: object,
) -> AsyncIterable[object]:
    """Async stream a LangGraph unchanged while recording one OpsCanvas run."""
    _raise_for_reserved_stream_kwargs(kwargs)
    modes = _effective_stream_modes(stream_modes)
    recorder = _build_recorder(
        graph,
        exporter=exporter,
        opscanvas_config=opscanvas_config,
        run_id=run_id,
        workflow_name=workflow_name,
        stream_modes=modes,
    )
    stream: AsyncIterable[object] | None = None

    try:
        merged_config = merge_opscanvas_callbacks(config, recorder)
        stream = await _call_astream(
            graph,
            input,
            config=merged_config,
            stream_modes=modes,
            stream_kwargs=kwargs,
        )
        async for chunk in stream:
            recorder.record_stream_chunk(chunk)
            yield chunk
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


def _raise_for_reserved_stream_kwargs(kwargs: Mapping[str, object]) -> None:
    reserved = sorted(_RESERVED_STREAM_KWARGS.intersection(kwargs))
    if reserved:
        names = ", ".join(reserved)
        raise TypeError(f"traced_stream manages these LangGraph stream kwargs: {names}")


async def _call_astream(
    graph: _AsyncStreamGraph,
    input: object,
    *,
    config: Mapping[str, object] | None,
    stream_modes: Sequence[str],
    stream_kwargs: Mapping[str, object],
) -> AsyncIterable[object]:
    result = graph.astream(
        input,
        config=config,
        version="v2",
        stream_mode=stream_modes,
        **stream_kwargs,
    )
    if inspect.isawaitable(result):
        result = await result
    return result
