from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable
from typing import Any, assert_never, cast

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from opscanvas_api.auth import require_api_key
from opscanvas_api.routes.health import router as health_router
from opscanvas_api.routes.ingest import router as ingest_router
from opscanvas_api.routes.runs import router as runs_router
from opscanvas_api.settings import Settings, get_settings
from opscanvas_api.store import ClickHouseRunStore, InMemoryRunStore, RunStore


def create_app() -> FastAPI:
    settings = get_settings()
    fastapi_app = FastAPI(title=settings.service_name, version=settings.version)
    fastapi_app.state.run_store = create_run_store(settings)
    _install_pre_body_auth_guard(fastapi_app, settings)
    fastapi_app.include_router(health_router)
    fastapi_app.include_router(ingest_router)
    fastapi_app.include_router(runs_router)
    return fastapi_app


def _install_pre_body_auth_guard(fastapi_app: FastAPI, settings: Settings) -> None:
    @fastapi_app.middleware("http")
    async def pre_body_auth_guard(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not _is_protected_path(request.url.path):
            return await call_next(request)

        try:
            require_api_key(
                settings=settings,
                authorization=request.headers.get("Authorization"),
            )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )

        return await call_next(request)


def _is_protected_path(path: str) -> bool:
    return path in {"/v1/chat/completions", "/v1/ingest", "/v1/runs"} or path.startswith(
        ("/v1/ingest/", "/v1/runs/")
    )


def create_run_store(settings: Settings) -> RunStore:
    if settings.store_backend == "memory":
        return InMemoryRunStore()
    if settings.store_backend == "clickhouse":
        return ClickHouseRunStore(_LazyClickHouseClient(settings))
    assert_never(settings.store_backend)


class _LazyClickHouseClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: object | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)

    def _resolve(self) -> object:
        if self._client is None:
            self._client = _create_clickhouse_client(self._settings)
        return self._client


def _create_clickhouse_client(settings: Settings) -> object:
    clickhouse_connect = importlib.import_module("clickhouse_connect")
    get_client = cast(Callable[..., object], clickhouse_connect.get_client)
    return get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_username,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        secure=settings.clickhouse_secure,
    )


app = create_app()
