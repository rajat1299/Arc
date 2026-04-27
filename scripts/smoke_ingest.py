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
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from opscanvas_core.schema_versions import CURRENT_SCHEMA_VERSION

DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_WEB_URL = "http://localhost:3000/"
EXPECTED_SPAN_KINDS = ["agent", "model_call", "tool_call", "retry", "model_call"]


@dataclass(frozen=True)
class SmokeResponse:
    status: int
    body: Any


class SmokeError(RuntimeError):
    """Raised when the local smoke check cannot complete successfully."""


def canonical_run_payload(run_id: str) -> dict[str, Any]:
    root_span_id = f"span_{run_id}_agent"
    plan_span_id = f"span_{run_id}_model_plan"
    tool_span_id = f"span_{run_id}_tool_fetch"
    retry_span_id = f"span_{run_id}_retry_parse"
    final_span_id = f"span_{run_id}_model_final"
    return {
        "id": run_id,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "status": "suboptimal",
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:08.200Z",
        "runtime": "smoke-ingest",
        "project_id": "project_smoke",
        "environment": "local",
        "tenant_id": "tenant_smoke",
        "user_id": "user_smoke",
        "workflow_name": "contract-review-triage",
        "usage": {
            "input_tokens": 3360,
            "output_tokens": 920,
            "cached_input_tokens": 1024,
            "reasoning_tokens": 260,
            "total_tokens": 4280,
            "cost_usd": 0.0642,
        },
        "metadata": {
            "source": "scripts/smoke_ingest.py",
            "customer": "Acme Legal",
            "priority": "standard",
            "ui_fixture": True,
        },
        "spans": [
            {
                "id": root_span_id,
                "run_id": run_id,
                "kind": "agent",
                "name": "ContractReviewAgent",
                "started_at": "2026-01-01T00:00:00Z",
                "ended_at": "2026-01-01T00:00:08.200Z",
                "usage": {
                    "input_tokens": 3360,
                    "output_tokens": 920,
                    "cached_input_tokens": 1024,
                    "reasoning_tokens": 260,
                    "total_tokens": 4280,
                    "cost_usd": 0.0642,
                },
                "input": {
                    "ticket_id": "ticket_1842",
                    "request": "Summarize renewal risk and recommend next action.",
                    "attachments": [{"type": "contract", "pages": 18}],
                },
                "output": {
                    "status": "completed_with_retry",
                    "recommendation": "Escalate renewal clause to legal ops.",
                    "confidence": 0.83,
                },
                "attributes": {
                    "agent.model": "gpt-5.1",
                    "agent.version": "2026-01-01",
                    "retry_count": 1,
                    "sla_ms": 10000,
                },
                "events": [
                    {
                        "id": f"evt_{run_id}_agent_started",
                        "span_id": root_span_id,
                        "name": "agent.started",
                        "timestamp": "2026-01-01T00:00:00Z",
                        "attributes": {"queue_ms": 42, "cold_start": False},
                    }
                ],
            },
            {
                "id": plan_span_id,
                "run_id": run_id,
                "kind": "model_call",
                "name": "gpt-5.1 plan extraction",
                "parent_id": root_span_id,
                "started_at": "2026-01-01T00:00:00.300Z",
                "ended_at": "2026-01-01T00:00:02.050Z",
                "usage": {
                    "input_tokens": 1480,
                    "output_tokens": 360,
                    "cached_input_tokens": 512,
                    "reasoning_tokens": 140,
                    "total_tokens": 1840,
                    "cost_usd": 0.0276,
                },
                "input": {
                    "model": "gpt-5.1",
                    "messages": [
                        {"role": "system", "content": "Extract contract review work plan."},
                        {"role": "user", "content": "Review ticket ticket_1842."},
                    ],
                },
                "output": {
                    "tool_plan": ["fetch_contract_terms"],
                    "risk_hypotheses": ["auto-renewal notice window", "price uplift cap"],
                },
                "attributes": {
                    "provider": "openai",
                    "temperature": 0.2,
                    "service_tier": "default",
                },
                "events": [],
            },
            {
                "id": tool_span_id,
                "run_id": run_id,
                "kind": "tool_call",
                "name": "fetch_contract_terms",
                "parent_id": root_span_id,
                "started_at": "2026-01-01T00:00:02.100Z",
                "ended_at": "2026-01-01T00:00:04.450Z",
                "usage": {"total_tokens": 0, "cost_usd": 0.0035},
                "input": {
                    "contract_id": "contract_2026_acme_renewal",
                    "fields": ["renewal_window", "uplift_cap", "termination_notice"],
                },
                "output": {
                    "renewal_window_days": 90,
                    "uplift_cap_percent": 7.5,
                    "termination_notice": "written_notice_required",
                },
                "attributes": {
                    "tool.category": "crm",
                    "cache_hit": False,
                    "http.status_code": 200,
                    "latency_ms": 2350,
                },
                "events": [
                    {
                        "id": f"evt_{run_id}_tool_completed",
                        "span_id": tool_span_id,
                        "name": "tool.completed",
                        "timestamp": "2026-01-01T00:00:04.450Z",
                        "attributes": {"ok": True, "records_returned": 3},
                    }
                ],
            },
            {
                "id": retry_span_id,
                "run_id": run_id,
                "kind": "retry",
                "name": "repair stale clause classification",
                "parent_id": root_span_id,
                "started_at": "2026-01-01T00:00:04.500Z",
                "ended_at": "2026-01-01T00:00:05.150Z",
                "usage": {
                    "input_tokens": 420,
                    "output_tokens": 120,
                    "total_tokens": 540,
                    "cost_usd": 0.0061,
                },
                "input": {
                    "classifier_output": {"renewal_risk": "low", "notice_window_days": 30},
                    "expected_notice_window_days": 90,
                },
                "output": {
                    "status": "recovered",
                    "renewal_risk": "medium",
                    "reason": "Notice window was read from an expired amendment.",
                },
                "attributes": {
                    "failure.kind": "stale_context",
                    "failure.severity": "suboptimal",
                    "retry.attempt": 1,
                },
                "events": [
                    {
                        "id": f"evt_{run_id}_suboptimal_detected",
                        "span_id": retry_span_id,
                        "name": "quality.suboptimal_detected",
                        "timestamp": "2026-01-01T00:00:04.620Z",
                        "attributes": {
                            "explanation": "Initial classification used a superseded amendment.",
                            "detected_by": "consistency_check",
                        },
                    },
                    {
                        "id": f"evt_{run_id}_retry_completed",
                        "span_id": retry_span_id,
                        "name": "retry.completed",
                        "timestamp": "2026-01-01T00:00:05.150Z",
                        "attributes": {"ok": True, "corrected_fields": ["renewal_risk"]},
                    },
                ],
            },
            {
                "id": final_span_id,
                "run_id": run_id,
                "kind": "model_call",
                "name": "gpt-5.1 final answer",
                "parent_id": root_span_id,
                "started_at": "2026-01-01T00:00:05.250Z",
                "ended_at": "2026-01-01T00:00:08.100Z",
                "usage": {
                    "input_tokens": 1460,
                    "output_tokens": 440,
                    "cached_input_tokens": 512,
                    "reasoning_tokens": 120,
                    "total_tokens": 1900,
                    "cost_usd": 0.0270,
                },
                "input": {
                    "model": "gpt-5.1",
                    "messages": [
                        {"role": "system", "content": "Write a concise legal ops recommendation."},
                        {
                            "role": "user",
                            "content": "Use recovered contract facts for ticket_1842.",
                        },
                    ],
                },
                "output": {
                    "summary": (
                        "Renewal risk is medium because notice is due 90 days before renewal."
                    ),
                    "next_action": (
                        "Ask legal ops to confirm whether notice should be sent this week."
                    ),
                    "citations": ["contract_2026_acme_renewal.section_8.2"],
                },
                "attributes": {
                    "provider": "openai",
                    "temperature": 0.1,
                    "finish_reason": "stop",
                },
                "events": [],
            },
        ],
    }


def expected_web_url(web_url: str, run_id: str) -> str:
    separator = "&" if "?" in web_url else "?"
    return f"{web_url}{separator}{urlencode({'runId': run_id})}"


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


def require_rich_spans(spans: Any, run_id: str, context: str) -> None:
    require(isinstance(spans, list), f"{context} spans response was not a JSON array")
    require(
        len(spans) == len(EXPECTED_SPAN_KINDS),
        f"{context} did not include the expected span tree",
    )

    span_by_id = {span.get("id"): span for span in spans if isinstance(span, dict)}
    root_span_id = f"span_{run_id}_agent"
    require(root_span_id in span_by_id, f"{context} missing root agent span")
    require(
        [span.get("kind") for span in spans] == EXPECTED_SPAN_KINDS,
        f"{context} span kinds changed",
    )
    require(
        all(span.get("run_id") == run_id for span in spans if isinstance(span, dict)),
        f"{context} included spans from a different run",
    )
    require(
        all(
            "input" in span
            and "output" in span
            and isinstance(span.get("attributes"), dict)
            and isinstance(span.get("usage"), dict)
            and span["usage"].get("cost_usd") is not None
            for span in spans
            if isinstance(span, dict)
        ),
        f"{context} spans did not include JSON input/output, attributes, and usage cost",
    )
    require(
        all(
            span.get("id") == root_span_id or span.get("parent_id") == root_span_id
            for span in spans
            if isinstance(span, dict)
        ),
        f"{context} did not preserve parent-child span links",
    )
    require(
        any(
            event.get("name") == "quality.suboptimal_detected"
            for span in spans
            if isinstance(span, dict)
            for event in span.get("events", [])
            if isinstance(event, dict)
        ),
        f"{context} missing suboptimal explanation event",
    )


def run_smoke(api_url: str, timeout: float, run_id: str | None, web_url: str) -> None:
    run_id = run_id or f"run_smoke_{int(time.time())}"
    payload = canonical_run_payload(run_id)

    print(f"API: {api_url}")

    ingest = request_json("POST", api_url, "/v1/ingest/runs", payload=payload, timeout=timeout)
    require(ingest.status == 202, f"Expected ingest status 202, got {ingest.status}")
    require(isinstance(ingest.body, dict), "Expected ingest response to be a JSON object")
    require(ingest.body.get("run_id") == run_id, "Ingest response did not echo the run ID")
    require(
        ingest.body.get("span_count") == len(EXPECTED_SPAN_KINDS),
        "Ingest response did not count the expected span tree",
    )
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
        run.body.get("usage", {}).get("cost_usd") == payload["usage"]["cost_usd"],
        "Run cost changed",
    )
    require_rich_spans(run.body.get("spans"), run_id, "Run detail")
    print(f"GET /v1/runs/{run_id} -> {run.status} returned {len(EXPECTED_SPAN_KINDS)} spans")

    spans = request_json("GET", api_url, f"/v1/runs/{run_id}/spans", timeout=timeout)
    require(spans.status == 200, f"Expected run spans status 200, got {spans.status}")
    require_rich_spans(spans.body, run_id, "Run spans endpoint")
    print(
        f"GET /v1/runs/{run_id}/spans -> {spans.status} "
        f"returned {len(EXPECTED_SPAN_KINDS)} spans"
    )

    metrics = request_json("GET", api_url, "/v1/runs/metrics", timeout=timeout)
    require(metrics.status == 200, f"Expected run metrics status 200, got {metrics.status}")
    require(isinstance(metrics.body, dict), "Expected metrics response to be a JSON object")
    require(
        metrics.body.get("total_cost_usd", 0) >= payload["usage"]["cost_usd"],
        "Metrics omitted run cost",
    )
    require(
        metrics.body.get("total_tokens", 0) >= payload["usage"]["total_tokens"],
        "Metrics omitted run tokens",
    )
    print(f"GET /v1/runs/metrics -> {metrics.status} includes smoke usage and cost")

    print("Smoke ingest passed")
    print(f"Open web UI: {expected_web_url(web_url, run_id)}")


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
    parser.add_argument(
        "--run-id",
        help="Optional deterministic run ID for repeatable UI testing.",
    )
    parser.add_argument(
        "--web-url",
        default=DEFAULT_WEB_URL,
        help=f"Base URL for the local web app. Defaults to {DEFAULT_WEB_URL}.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run_smoke(
            api_url=args.api_url,
            timeout=args.timeout,
            run_id=args.run_id,
            web_url=args.web_url,
        )
    except SmokeError as error:
        print(f"Smoke ingest failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
