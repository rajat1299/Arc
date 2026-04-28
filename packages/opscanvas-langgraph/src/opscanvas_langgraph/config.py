"""Configuration for the OpsCanvas LangGraph plugin."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_ENVIRONMENT = "development"
DEFAULT_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class OpsCanvasConfig:
    """Runtime configuration for the OpsCanvas LangGraph integration."""

    endpoint: str | None = None
    api_key: str | None = None
    project_id: str | None = None
    environment: str = DEFAULT_ENVIRONMENT
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> OpsCanvasConfig:
        """Load configuration from ``OPSCANVAS_*`` environment variables."""
        values = os.environ if environ is None else environ
        timeout = values.get("OPSCANVAS_TIMEOUT_SECONDS")

        return cls(
            endpoint=_empty_to_none(values.get("OPSCANVAS_ENDPOINT")),
            api_key=_empty_to_none(values.get("OPSCANVAS_API_KEY")),
            project_id=_empty_to_none(values.get("OPSCANVAS_PROJECT_ID")),
            environment=values.get("OPSCANVAS_ENVIRONMENT", DEFAULT_ENVIRONMENT)
            or DEFAULT_ENVIRONMENT,
            timeout_seconds=float(timeout) if timeout else DEFAULT_TIMEOUT_SECONDS,
        )


def _empty_to_none(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return value
