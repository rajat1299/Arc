from fastapi import FastAPI

from opscanvas_api.routes.health import router as health_router
from opscanvas_api.routes.ingest import router as ingest_router
from opscanvas_api.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    fastapi_app = FastAPI(title=settings.service_name, version=settings.version)
    fastapi_app.include_router(health_router)
    fastapi_app.include_router(ingest_router)
    return fastapi_app


app = create_app()
