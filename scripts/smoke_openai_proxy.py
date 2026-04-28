#!/usr/bin/env python3
"""Exercise the OpsCanvas OpenAI-compatible proxy against a configured API."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_PROMPT = "Reply with a short health check sentence."


@dataclass(frozen=True)
class SmokeResponse:
    status: int
    body: Any


class SmokeError(RuntimeError):
    """Raised when the OpenAI proxy smoke check cannot complete successfully."""


def request_json(
    method: str,
    api_url: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    api_key: str | None = None,
    timeout: float,
    include_query: dict[str, str] | None = None,
) -> SmokeResponse:
    url = urljoin(api_url.rstrip("/") + "/", path.lstrip("/"))
    if include_query:
        url = f"{url}?{urlencode(include_query)}"

    data = None
    headers = {"Accept": "application/json"}
    if api_key is not None:
        headers["Authorization"] = f"Bearer {api_key}"
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
        message = f"{method} {path} failed with HTTP {error.code}: {error.reason}"
        raise SmokeError(message) from error
    except URLError as error:
        raise SmokeError(f"{method} {path} could not reach {api_url}: {error.reason}") from error
    except TimeoutError as error:
        raise SmokeError(f"{method} {path} timed out after {timeout:g}s") from error
    except json.JSONDecodeError as error:
        raise SmokeError(f"{method} {path} returned invalid JSON") from error


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def chat_completion_payload(model: str, prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }


def format_nullable(value: object) -> str:
    return "null" if value is None else str(value)


def run_smoke(
    *,
    api_url: str,
    api_key: str | None,
    model: str,
    prompt: str,
    timeout: float,
) -> None:
    print(f"API: {api_url}")
    print(f"POST /v1/chat/completions model={model}")

    completion = request_json(
        "POST",
        api_url,
        "/v1/chat/completions",
        payload=chat_completion_payload(model, prompt),
        api_key=api_key,
        timeout=timeout,
    )
    require(completion.status == 200, f"Expected proxy status 200, got {completion.status}")
    require(isinstance(completion.body, dict), "Expected proxy response to be a JSON object")
    completion_id = completion.body.get("id", "<missing id>")
    usage = completion.body.get("usage")
    response_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
    print(
        "POST /v1/chat/completions -> "
        f"{completion.status} id={completion_id} response_tokens={format_nullable(response_tokens)}"
    )

    runs = request_json(
        "GET",
        api_url,
        "/v1/runs",
        api_key=api_key,
        timeout=timeout,
        include_query={"runtime": "openai-compatible-proxy", "limit": "1"},
    )
    require(runs.status == 200, f"Expected runs status 200, got {runs.status}")
    require(isinstance(runs.body, list), "Expected runs response to be a JSON array")
    require(len(runs.body) >= 1, "No OpenAI-compatible proxy runs found")
    latest_run = runs.body[0]
    require(isinstance(latest_run, dict), "Latest run summary was not a JSON object")

    print(
        "GET /v1/runs?runtime=openai-compatible-proxy&limit=1 -> "
        f"{runs.status} id={latest_run.get('id')} status={latest_run.get('status')} "
        f"cost_usd={format_nullable(latest_run.get('cost_usd'))} "
        f"tokens={format_nullable(latest_run.get('total_tokens'))}"
    )
    print("OpenAI proxy smoke passed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Post a non-streaming OpenAI-compatible Chat Completions request through "
            "OpsCanvas and query the latest proxy run. The API must be configured with "
            "OPSCANVAS_API_OPENAI_PROXY_ENABLED=true and "
            "OPSCANVAS_API_OPENAI_UPSTREAM_API_KEY. Pass --api-key when OpsCanvas API "
            "auth is enabled."
        )
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"Base URL for the OpsCanvas API. Defaults to {DEFAULT_API_URL}.",
    )
    parser.add_argument(
        "--api-key",
        help="Optional OpsCanvas bearer API key. Required when API auth is enabled.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model name to send through the proxy. Defaults to {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Prompt text to send. The script does not print the raw prompt.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds. Defaults to 30.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run_smoke(
            api_url=args.api_url,
            api_key=args.api_key,
            model=args.model,
            prompt=args.prompt,
            timeout=args.timeout,
        )
    except SmokeError as error:
        print(f"OpenAI proxy smoke failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
