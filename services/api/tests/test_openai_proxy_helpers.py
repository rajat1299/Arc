import json
from datetime import UTC, datetime

import pytest
from opscanvas_api.openai_proxy import (
    OPENAI_CHAT_COMPLETIONS_PATH,
    OPENAI_PROXY_RUNTIME,
    OPENAI_PROXY_WORKFLOW_NAME,
    build_proxy_run,
    build_upstream_url,
    forward_request_headers,
    forward_response_headers,
    summarize_chat_request,
    summarize_chat_response,
    usage_from_openai,
    validate_upstream_base_url,
)
from opscanvas_core.events import RunStatus, SpanKind, Usage

STARTED_AT = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)
ENDED_AT = datetime(2026, 4, 28, 12, 0, 1, tzinfo=UTC)


def test_build_upstream_url_joins_base_and_chat_completions_path() -> None:
    assert (
        build_upstream_url("https://api.openai.com/v1", "/chat/completions")
        == "https://api.openai.com/v1/chat/completions"
    )
    assert (
        build_upstream_url("https://gateway.example/root/", "chat/completions")
        == "https://gateway.example/root/chat/completions"
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.openai.com/v1",
        "http://localhost:8000/v1",
        "http://127.0.0.1:8000/v1",
        "http://testserver/v1",
    ],
)
def test_validate_upstream_base_url_allows_https_and_local_http(base_url: str) -> None:
    validate_upstream_base_url(base_url)


@pytest.mark.parametrize(
    "base_url",
    ["", "ftp://api.openai.com/v1", "http://api.openai.com/v1", "http://192.168.1.1/v1"],
)
def test_validate_upstream_base_url_rejects_unsafe_values(base_url: str) -> None:
    with pytest.raises(ValueError):
        validate_upstream_base_url(base_url)


def test_forward_request_headers_filters_unsafe_headers_and_injects_upstream_auth() -> None:
    forwarded = forward_request_headers(
        {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "OpenAI-Organization": "org_safe",
            "OpenAI-Project": "proj_safe",
            "Idempotency-Key": "idem_safe",
            "X-Request-ID": "req_safe",
            "X-Client-Request-ID": "client_safe",
            "Authorization": "Bearer opscanvas-key",
            "Cookie": "session=secret",
            "Host": "proxy.local",
            "Content-Length": "999",
            "Transfer-Encoding": "chunked",
            "X-OpsCanvas-Debug": "secret",
            "X-Unknown": "drop",
        },
        upstream_api_key="sk-upstream-secret",
    )

    assert forwarded == {
        "content-type": "application/json",
        "accept": "application/json",
        "openai-organization": "org_safe",
        "openai-project": "proj_safe",
        "idempotency-key": "idem_safe",
        "x-request-id": "req_safe",
        "x-client-request-id": "client_safe",
        "Authorization": "Bearer sk-upstream-secret",
    }


def test_forward_response_headers_filters_to_safe_response_headers() -> None:
    forwarded = forward_response_headers(
        {
            "Content-Type": "application/json",
            "X-Request-ID": "req_upstream",
            "OpenAI-Organization": "org_safe",
            "OpenAI-Processing-MS": "123",
            "OpenAI-Version": "2020-10-01",
            "X-RateLimit-Limit-Requests": "500",
            "Set-Cookie": "session=secret",
            "Cookie": "session=secret",
            "Authorization": "Bearer secret",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked",
            "X-Unknown": "drop",
        }
    )

    assert forwarded == {
        "content-type": "application/json",
        "x-request-id": "req_upstream",
        "openai-organization": "org_safe",
        "openai-processing-ms": "123",
        "openai-version": "2020-10-01",
        "x-ratelimit-limit-requests": "500",
    }


def test_usage_from_openai_maps_token_usage_details() -> None:
    assert usage_from_openai(
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 25,
                "total_tokens": 125,
                "prompt_tokens_details": {"cached_tokens": 40},
                "completion_tokens_details": {"reasoning_tokens": 7},
            }
        }
    ) == Usage(
        input_tokens=100,
        output_tokens=25,
        cached_input_tokens=40,
        reasoning_tokens=7,
        total_tokens=125,
    )


def test_usage_from_openai_returns_none_when_usage_is_absent() -> None:
    assert usage_from_openai({"id": "chatcmpl_123"}) is None


def test_chat_summaries_include_only_bounded_safe_facts() -> None:
    request_summary = summarize_chat_request(
        {
            "model": "gpt-4.1-mini",
            "messages": [
                {"role": "user", "content": "raw prompt secret"},
                {"role": "assistant", "content": "raw context secret"},
            ],
            "tools": [{"function": {"name": "lookup", "parameters": {"secret_arg": "value"}}}],
            "stream": False,
            "temperature": 0.2,
            "metadata": {"safe_count_only": "secret metadata value"},
        }
    )
    response_summary = summarize_chat_response(
        {
            "id": "chatcmpl_123",
            "model": "gpt-4.1-mini",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "raw completion secret"},
                }
            ],
            "usage": {"total_tokens": 10},
        }
    )

    assert request_summary == {
        "model": "gpt-4.1-mini",
        "message_count": 2,
        "tool_count": 1,
        "stream": False,
        "temperature_present": True,
        "top_p_present": False,
        "metadata_key_count": 1,
    }
    assert response_summary == {
        "id": "chatcmpl_123",
        "model": "gpt-4.1-mini",
        "choice_count": 1,
        "finish_reasons": ["stop"],
        "usage_present": True,
    }
    assert "raw prompt secret" not in json.dumps(request_summary)
    assert "secret_arg" not in json.dumps(request_summary)
    assert "raw completion secret" not in json.dumps(response_summary)


def test_build_proxy_run_creates_canonical_succeeded_model_call_run() -> None:
    run = build_proxy_run(
        request_payload={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "raw prompt secret"}],
            "stream": False,
        },
        response_payload={
            "id": "chatcmpl_123",
            "model": "gpt-4.1-mini",
            "choices": [{"finish_reason": "stop", "message": {"content": "raw completion secret"}}],
            "service_tier": "default",
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        },
        upstream_status_code=200,
        started_at=STARTED_AT,
        ended_at=ENDED_AT,
        response_headers={"x-request-id": "req_upstream"},
    )

    assert run.id.startswith("run_")
    assert run.status is RunStatus.succeeded
    assert run.runtime == OPENAI_PROXY_RUNTIME
    assert run.workflow_name == OPENAI_PROXY_WORKFLOW_NAME
    assert run.started_at == STARTED_AT
    assert run.ended_at == ENDED_AT
    assert run.usage == Usage(input_tokens=10, output_tokens=4, total_tokens=14)
    assert run.metadata == {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "status": "succeeded",
        "proxy.upstream_path": OPENAI_CHAT_COMPLETIONS_PATH,
        "proxy.upstream_status_code": 200,
        "openai.request_id": "req_upstream",
    }

    assert len(run.spans) == 1
    span = run.spans[0]
    assert span.id.startswith("span_")
    assert span.run_id == run.id
    assert span.kind is SpanKind.model_call
    assert span.name == OPENAI_PROXY_WORKFLOW_NAME
    assert span.started_at == STARTED_AT
    assert span.ended_at == ENDED_AT
    assert span.usage == run.usage
    assert span.input_data == {
        "model": "gpt-4.1-mini",
        "message_count": 1,
        "tool_count": 0,
        "stream": False,
        "temperature_present": False,
        "top_p_present": False,
        "metadata_key_count": 0,
    }
    assert span.output_data == {
        "id": "chatcmpl_123",
        "model": "gpt-4.1-mini",
        "choice_count": 1,
        "finish_reasons": ["stop"],
        "usage_present": True,
    }
    assert span.attributes == {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "status": "succeeded",
        "http.status_code": 200,
        "upstream_path": OPENAI_CHAT_COMPLETIONS_PATH,
        "openai.request_id": "req_upstream",
        "openai.response_id": "chatcmpl_123",
        "service_tier": "default",
    }


def test_build_proxy_run_marks_non_2xx_failed_and_omits_raw_secrets_from_serialized_json() -> None:
    run = build_proxy_run(
        request_payload={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "never persist this prompt"}],
            "tools": [{"function": {"arguments": '{"password":"tool-secret"}'}}],
            "metadata": {"api_key": "sk-should-not-persist"},
        },
        response_payload={
            "error": {"message": "provider error"},
            "choices": [{"message": {"content": "never persist this completion"}}],
        },
        upstream_status_code=400,
        started_at=STARTED_AT,
        ended_at=ENDED_AT,
        response_headers={"set-cookie": "session=cookie-secret"},
    )

    serialized = run.model_dump_json(by_alias=True)

    assert run.status is RunStatus.failed
    assert run.spans[0].attributes["provider"] == "openai"
    assert run.spans[0].attributes["model"] == "gpt-4.1-mini"
    for secret in [
        "never persist this prompt",
        "never persist this completion",
        "sk-should-not-persist",
        "tool-secret",
        "cookie-secret",
    ]:
        assert secret not in serialized
