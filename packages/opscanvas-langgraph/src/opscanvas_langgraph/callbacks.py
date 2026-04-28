"""LangGraph callback helpers for recording lifecycle events."""

from __future__ import annotations

from copy import copy
from typing import TYPE_CHECKING, Protocol, TypeGuard

if TYPE_CHECKING:
    from collections.abc import Mapping

    from opscanvas_langgraph.recorder import LangGraphRunRecorder

try:
    from langgraph.callbacks import (  # type: ignore[import-not-found]
        GraphCallbackHandler as _GraphCallbackHandler,
    )
except ImportError:
    _GraphCallbackHandler = object
    _LANGGRAPH_IMPORTABLE = False
else:
    _LANGGRAPH_IMPORTABLE = True


class _CallbackManagerLike(Protocol):
    def add_handler(self, handler: object, *, inherit: bool = True) -> None: ...


def get_langgraph_install_error() -> str:
    """Return the shared user-facing LangGraph installation guidance."""
    return (
        "LangGraph is required for OpsCanvas LangGraph callbacks. "
        "Install it with `pip install 'opscanvas-langgraph[langgraph]'` "
        "or `pip install langgraph`."
    )


class OpsCanvasGraphCallbackHandler(_GraphCallbackHandler):  # type: ignore[misc]
    """Record public LangGraph interrupt and resume callback events."""

    def __init__(self, recorder: LangGraphRunRecorder) -> None:
        if not _LANGGRAPH_IMPORTABLE:
            raise RuntimeError(get_langgraph_install_error())
        super().__init__()
        self.recorder = recorder

    def on_interrupt(self, event: object) -> None:
        """Record a LangGraph interrupt lifecycle event."""
        self.recorder.record_interrupt(event)

    def on_resume(self, event: object) -> None:
        """Record a LangGraph resume lifecycle event."""
        self.recorder.record_resume(event)


def merge_opscanvas_callbacks(
    config: Mapping[str, object] | None,
    recorder: LangGraphRunRecorder,
) -> dict[str, object]:
    """Return a shallow-copied LangGraph config with OpsCanvas callbacks appended."""
    merged = dict(config or {})
    handler = OpsCanvasGraphCallbackHandler(recorder)

    callbacks = merged.get("callbacks")
    if callbacks is None:
        merged["callbacks"] = [handler]
        return merged

    if _is_callback_manager(callbacks):
        copied_callbacks = copy(callbacks)
        copied_callbacks.add_handler(handler, inherit=True)
        merged["callbacks"] = copied_callbacks
        return merged

    if isinstance(callbacks, list):
        merged["callbacks"] = [*callbacks, handler]
        return merged

    if isinstance(callbacks, tuple):
        merged["callbacks"] = (*callbacks, handler)
        return merged

    merged["callbacks"] = [callbacks, handler]
    return merged


def _is_callback_manager(callbacks: object) -> TypeGuard[_CallbackManagerLike]:
    if isinstance(callbacks, list | tuple):
        return False
    if not hasattr(callbacks, "add_handler"):
        return False
    return callable(callbacks.add_handler)
