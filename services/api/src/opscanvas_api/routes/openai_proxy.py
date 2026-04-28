from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Protocol, cast

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from opscanvas_api.auth import require_api_key
from opscanvas_api.openai_proxy import (
    OPENAI_CHAT_COMPLETIONS_PATH,
    build_proxy_run,
    build_upstream_url,
    forward_request_headers,
    forward_response_headers,
)
from opscanvas_api.routes.runs import get_run_store
from opscanvas_api.settings import Settings, get_settings
from opscanvas_api.store import RunStore

router = APIRouter(tags=["openai-proxy"], dependencies=[Depends(require_api_key)])


class OpenAIProxyHttpClient(Protocol):
    async def post(
        self,
        url: str,
        *,
        json: Mapping[str, object],
        headers: Mapping[str, str],
    ) -> httpx.Response: ...


@router.post("/v1/chat/completions/", include_in_schema=False)
@router.post("/v1/chat/completions")
async def proxy_chat_completions(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    run_store: Annotated[RunStore, Depends(get_run_store)],
) -> Response:
    if not settings.openai_proxy_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    upstream_api_key = settings.openai_upstream_api_key.strip()
    if not upstream_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI proxy upstream API key is not configured.",
        )

    payload = await _json_object_body(request)
    if payload.get("stream") is True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Streaming is not supported by the OpsCanvas OpenAI proxy v0.",
        )

    try:
        upstream_url = build_upstream_url(
            settings.openai_upstream_base_url,
            OPENAI_CHAT_COMPLETIONS_PATH,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI proxy upstream base URL is invalid.",
        ) from error

    started_at = datetime.now(UTC)
    try:
        upstream_response = await _post_upstream(
            request=request,
            settings=settings,
            upstream_url=upstream_url,
            upstream_api_key=upstream_api_key,
            payload=payload,
        )
    except httpx.TransportError:
        ended_at = datetime.now(UTC)
        run_store.upsert(
            build_proxy_run(
                request_payload=payload,
                response_payload=None,
                upstream_status_code=status.HTTP_502_BAD_GATEWAY,
                started_at=started_at,
                ended_at=ended_at,
            )
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenAI upstream request failed.",
        ) from None

    ended_at = datetime.now(UTC)
    response_payload = _json_object_response(upstream_response)
    safe_response_headers = forward_response_headers(upstream_response.headers)
    run_store.upsert(
        build_proxy_run(
            request_payload=payload,
            response_payload=response_payload,
            upstream_status_code=upstream_response.status_code,
            started_at=started_at,
            ended_at=ended_at,
            response_headers=safe_response_headers,
        )
    )
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=safe_response_headers,
        media_type=_response_media_type(safe_response_headers),
    )


async def _json_object_body(request: Request) -> dict[str, object]:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(
            status_code=422,
            detail="Request body must be a JSON object.",
        ) from error

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=422,
            detail="Request body must be a JSON object.",
        )
    return cast(dict[str, object], payload)


async def _post_upstream(
    *,
    request: Request,
    settings: Settings,
    upstream_url: str,
    upstream_api_key: str,
    payload: Mapping[str, object],
) -> httpx.Response:
    headers = forward_request_headers(request.headers, upstream_api_key)
    injected_client = getattr(request.app.state, "openai_proxy_http_client", None)
    if injected_client is not None:
        client = cast(OpenAIProxyHttpClient, injected_client)
        return await client.post(upstream_url, json=payload, headers=headers)

    timeout = httpx.Timeout(settings.openai_proxy_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(upstream_url, json=payload, headers=headers)


def _json_object_response(response: httpx.Response) -> Mapping[str, object] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, Mapping):
        return None
    return cast(Mapping[str, object], payload)


def _response_media_type(headers: Mapping[str, str]) -> str | None:
    content_type = headers.get("content-type")
    if content_type is None:
        return None
    return content_type.split(";", 1)[0].strip() or None
