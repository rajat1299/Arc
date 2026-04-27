"""HTTP client for OpsCanvas ingestion APIs."""

from __future__ import annotations

import httpx
from opscanvas_core import Run

from opscanvas_claude.config import OpsCanvasConfig


class OpsCanvasClientError(RuntimeError):
    """Raised when the OpsCanvas API rejects an ingest request."""


class OpsCanvasClient:
    """Submit canonical OpsCanvas payloads to the ingest API."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        *,
        config: OpsCanvasConfig | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        effective_config = config or OpsCanvasConfig.from_env()
        self.endpoint = (endpoint or effective_config.endpoint or "").rstrip("/")
        self.api_key = api_key if api_key is not None else effective_config.api_key
        self._client = http_client or httpx.Client(timeout=effective_config.timeout_seconds)

        if not self.endpoint:
            raise ValueError("OpsCanvas endpoint is required to create an OpsCanvasClient")

    def ingest_run(self, run: Run) -> None:
        """POST a canonical run payload to ``/v1/ingest/runs``."""
        response = self._client.post(
            f"{self.endpoint}/v1/ingest/runs",
            json=run.model_dump(mode="json", by_alias=True),
            headers=self._headers(),
        )
        if response.is_success:
            return

        raise OpsCanvasClientError(
            f"OpsCanvas ingest failed with HTTP {response.status_code}: {response.text}"
        )

    def _headers(self) -> dict[str, str]:
        if self.api_key is None:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}
