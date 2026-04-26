#!/usr/bin/env python3
"""Post and query a canonical OpsCanvas Run against a local API."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from opscanvas_core.schema_versions import CURRENT_SCHEMA_VERSION

DEFAULT_API_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class SmokeResponse:
    status: int
    body: Any


class SmokeError(RuntimeError):
    """Raised when the local smoke check cannot complete successfully."""


def canonical_run_payload(run_id: str) -> dict[str, Any]:
    span_id = f"span_{run_id}"
    event_id = f"evt_{run_id}"
    return {
        "id": run_id,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "status": "succeeded",
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:03Z",
        "runtime": "smoke-ingest",
        "project_id": "project_smoke",
        "environment": "local",
        "tenant_id": "tenant_smoke",
        "workflow_name": "local-smoke-ingest",
        "usage": {"total_tokens": 18, "cost_usd": 0.02},
        "metadata": {"source": "scripts/smoke_ingest.py"},
        "spans": [
            {
                "id": span_id,
                "run_id": run_id,
                "kind": "tool_call",
                "name": "search",
                "started_at": "2026-01-01T00:00:01Z",
                "ended_at": "2026-01-01T00:00:02Z",
                "input": {"query": "contract"},
                "output": {"count": 1},
                "events": [
                    {
                        "id": event_id,
                        "span_id": span_id,
                        "name": "tool.completed",
                        "timestamp": "2026-01-01T00:00:02Z",
                        "attributes": {"ok": True},
                    }
                ],
            }
        ],
    }


def request_json(
    method: str,
    api_url: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float,
) -> SmokeResponse:
    url = urljoin(api_url.rstrip("/") + "/", path.lstrip("/"))
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else None
            return SmokeResponse(status=response.status, body=body)
    except HTTPError as error:
        raw = error.read().decode("utf-8")
        detail = raw or error.reason
        raise SmokeError(f"{method} {path} failed with HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise SmokeError(f"{method} {path} could not reach {api_url}: {error.reason}") from error
    except TimeoutError as error:
        raise SmokeError(f"{method} {path} timed out after {timeout:g}s") from error
    except json.JSONDecodeError as error:
        raise SmokeError(f"{method} {path} returned invalid JSON") from error


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def run_smoke(api_url: str, timeout: float) -> None:
    run_id = f"run_smoke_{int(time.time())}"
    payload = canonical_run_payload(run_id)

    print(f"API: {api_url}")

    ingest = request_json("POST", api_url, "/v1/ingest/runs", payload=payload, timeout=timeout)
    require(ingest.status == 202, f"Expected ingest status 202, got {ingest.status}")
    require(isinstance(ingest.body, dict), "Expected ingest response to be a JSON object")
    require(ingest.body.get("run_id") == run_id, "Ingest response did not echo the run ID")
    print(f"POST /v1/ingest/runs -> {ingest.status} accepted {run_id}")

    runs = request_json("GET", api_url, "/v1/runs", timeout=timeout)
    require(runs.status == 200, f"Expected run list status 200, got {runs.status}")
    require(isinstance(runs.body, list), "Expected run list response to be a JSON array")
    require(
        any(run.get("id") == run_id for run in runs.body if isinstance(run, dict)),
        "Run missing from /v1/runs",
    )
    print(f"GET /v1/runs -> {runs.status} found {run_id}")

    run = request_json("GET", api_url, f"/v1/runs/{run_id}", timeout=timeout)
    require(run.status == 200, f"Expected run detail status 200, got {run.status}")
    require(isinstance(run.body, dict), "Expected run detail response to be a JSON object")
    require(run.body.get("id") == run_id, "Run detail response returned the wrong run")
    require(
        len(run.body.get("spans", [])) == 1,
        "Run detail response did not include the sample span",
    )
    print(f"GET /v1/runs/{run_id} -> {run.status} returned 1 span")

    print("Smoke ingest passed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Post a canonical sample Run to a local OpsCanvas API and query it back."
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"Base URL for the local API. Defaults to {DEFAULT_API_URL}.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Request timeout in seconds. Defaults to 5.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run_smoke(api_url=args.api_url, timeout=args.timeout)
    except SmokeError as error:
        print(f"Smoke ingest failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
