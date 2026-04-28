"""Pure helpers for OpenAI-compatible proxy mapping."""

from collections.abc import Mapping
from datetime import datetime
from urllib.parse import SplitResult, urlsplit, urlunsplit

from opscanvas_core.events import Run, RunStatus, Span, SpanKind, Usage
from opscanvas_core.ids import generate_run_id, generate_span_id
from pydantic import JsonValue

OPENAI_PROXY_RUNTIME = "openai-compatible-proxy"
OPENAI_PROXY_WORKFLOW_NAME = "openai.chat.completions.create"
OPENAI_CHAT_COMPLETIONS_PATH = "/chat/completions"
OPENAI_PROVIDER = "openai"
_MAX_SUMMARY_STRING_LENGTH = 200
_MAX_FINISH_REASONS = 16

_LOCAL_HTTP_HOSTS = frozenset({"localhost", "127.0.0.1", "testserver"})
_REQUEST_HEADER_ALLOWLIST = frozenset(
    {
        "content-type",
        "accept",
        "openai-organization",
        "openai-project",
        "idempotency-key",
        "x-request-id",
        "x-client-request-id",
    }
)
_RESPONSE_HEADER_ALLOWLIST = frozenset(
    {
        "content-type",
        "x-request-id",
        "openai-organization",
        "openai-processing-ms",
        "openai-version",
    }
)


def build_upstream_url(base_url: str, path: str) -> str:
    """Join a configured upstream base URL to a fixed proxy path."""
    parsed = _validated_upstream_base_url(base_url)
    normalized_base_url = urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")
    )
    return f"{normalized_base_url}/{path.lstrip('/')}"


def validate_upstream_base_url(base_url: str) -> None:
    """Validate the upstream base URL against the v0 proxy security policy."""
    _validated_upstream_base_url(base_url)


def _validated_upstream_base_url(base_url: str) -> SplitResult:
    stripped = base_url.strip()
    if not stripped:
        raise ValueError("OpenAI upstream base URL must not be empty.")

    parsed = urlsplit(stripped)
    if parsed.query or parsed.fragment:
        raise ValueError("OpenAI upstream base URL must not include a query or fragment.")

    if parsed.scheme == "https":
        if not parsed.netloc:
            raise ValueError("OpenAI upstream base URL must include a host.")
        return parsed

    if parsed.scheme == "http":
        hostname = parsed.hostname or ""
        if hostname.lower() in _LOCAL_HTTP_HOSTS:
            return parsed
        raise ValueError("OpenAI upstream base URL may use http only for local test hosts.")

    raise ValueError("OpenAI upstream base URL must use https.")


def forward_request_headers(headers: Mapping[str, str], upstream_api_key: str) -> dict[str, str]:
    """Return request headers that are safe to forward to the upstream provider."""
    forwarded = {
        name.lower(): value
        for name, value in headers.items()
        if name.lower() in _REQUEST_HEADER_ALLOWLIST
    }
    forwarded["Authorization"] = f"Bearer {upstream_api_key}"
    return forwarded


def forward_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return response headers that are safe to forward to the proxy caller."""
    forwarded: dict[str, str] = {}
    for name, value in headers.items():
        normalized = name.lower()
        if normalized in _RESPONSE_HEADER_ALLOWLIST or normalized.startswith("x-ratelimit-"):
            forwarded[normalized] = value
    return forwarded


def usage_from_openai(payload: Mapping[str, object]) -> Usage | None:
    """Map OpenAI token usage fields to canonical OpsCanvas usage."""
    usage_payload = payload.get("usage")
    if not isinstance(usage_payload, Mapping):
        return None

    values = {
        "input_tokens": _non_negative_int(usage_payload.get("prompt_tokens")),
        "output_tokens": _non_negative_int(usage_payload.get("completion_tokens")),
        "cached_input_tokens": _nested_non_negative_int(
            usage_payload, "prompt_tokens_details", "cached_tokens"
        ),
        "reasoning_tokens": _nested_non_negative_int(
            usage_payload, "completion_tokens_details", "reasoning_tokens"
        ),
        "total_tokens": _non_negative_int(usage_payload.get("total_tokens")),
    }
    if all(value is None for value in values.values()):
        return None
    return Usage.model_validate(values)


def summarize_chat_request(payload: Mapping[str, object]) -> JsonValue:
    """Summarize a Chat Completions request without retaining prompt/tool data."""
    summary: dict[str, JsonValue] = {
        "model": _string_value(payload.get("model")),
        "message_count": _sequence_count(payload.get("messages")),
        "tool_count": _sequence_count(payload.get("tools")),
        "stream": _bool_or_none(payload.get("stream")),
        "temperature_present": "temperature" in payload,
        "top_p_present": "top_p" in payload,
        "metadata_key_count": _mapping_count(payload.get("metadata")),
    }
    return summary


def summarize_chat_response(payload: Mapping[str, object]) -> JsonValue:
    """Summarize a Chat Completions response without retaining assistant output."""
    choices = payload.get("choices")
    choice_list = choices if isinstance(choices, list) else []
    finish_reasons: list[JsonValue] = [
        finish_reason
        for choice in choice_list[:_MAX_FINISH_REASONS]
        if isinstance(choice, Mapping)
        for finish_reason in [_string_value(choice.get("finish_reason"))]
        if finish_reason is not None
    ]
    summary: dict[str, JsonValue] = {
        "id": _string_value(payload.get("id")),
        "model": _string_value(payload.get("model")),
        "choice_count": len(choice_list),
        "finish_reasons": finish_reasons,
        "usage_present": isinstance(payload.get("usage"), Mapping),
    }
    return summary


def build_proxy_run(
    *,
    request_payload: Mapping[str, object],
    response_payload: Mapping[str, object] | None,
    upstream_status_code: int,
    started_at: datetime,
    ended_at: datetime,
    response_headers: Mapping[str, str] | None = None,
) -> Run:
    """Create a canonical run for a proxied Chat Completions request."""
    run_id = generate_run_id()
    span_id = generate_span_id()
    status = RunStatus.succeeded if 200 <= upstream_status_code <= 299 else RunStatus.failed
    model = (
        _string_value(response_payload.get("model")) if response_payload is not None else None
    ) or _string_value(request_payload.get("model")) or "unknown"
    usage = usage_from_openai(response_payload) if response_payload is not None else None
    request_summary = summarize_chat_request(request_payload)
    response_summary = (
        summarize_chat_response(response_payload) if response_payload is not None else None
    )
    response_id = (
        _string_value(response_payload.get("id")) if response_payload is not None else None
    )
    service_tier = _service_tier_from_response(response_payload)

    run_metadata: dict[str, JsonValue] = {
        "provider": OPENAI_PROVIDER,
        "model": model,
        "status": status.value,
        "proxy.upstream_path": OPENAI_CHAT_COMPLETIONS_PATH,
        "proxy.upstream_status_code": upstream_status_code,
    }
    request_id = _upstream_request_id(response_headers)
    if request_id is not None:
        run_metadata["openai.request_id"] = request_id

    span_attributes: dict[str, JsonValue] = {
        "provider": OPENAI_PROVIDER,
        "model": model,
        "status": status.value,
        "http.status_code": upstream_status_code,
        "upstream_path": OPENAI_CHAT_COMPLETIONS_PATH,
    }
    if request_id is not None:
        span_attributes["openai.request_id"] = request_id
    if response_id is not None:
        span_attributes["openai.response_id"] = response_id
    if service_tier is not None:
        span_attributes["service_tier"] = service_tier

    span = Span(
        id=span_id,
        run_id=run_id,
        kind=SpanKind.model_call,
        name=OPENAI_PROXY_WORKFLOW_NAME,
        started_at=started_at,
        ended_at=ended_at,
        usage=usage,
        input=request_summary,
        output=response_summary,
        attributes=span_attributes,
    )
    return Run(
        id=run_id,
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        runtime=OPENAI_PROXY_RUNTIME,
        workflow_name=OPENAI_PROXY_WORKFLOW_NAME,
        usage=usage,
        metadata=run_metadata,
        spans=[span],
    )


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _nested_non_negative_int(
    payload: Mapping[object, object], parent_key: str, child_key: str
) -> int | None:
    parent = payload.get(parent_key)
    if not isinstance(parent, Mapping):
        return None
    return _non_negative_int(parent.get(child_key))


def _string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value[:_MAX_SUMMARY_STRING_LENGTH]


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _sequence_count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def _mapping_count(value: object) -> int:
    return len(value) if isinstance(value, Mapping) else 0


def _upstream_request_id(headers: Mapping[str, str] | None) -> str | None:
    if headers is None:
        return None
    safe_headers = forward_response_headers(headers)
    return safe_headers.get("x-request-id")


def _service_tier_from_response(response_payload: Mapping[str, object] | None) -> str | None:
    if response_payload is None:
        return None
    return _string_value(response_payload.get("service_tier"))
