from typing import Annotated, TypedDict

from fastapi import APIRouter, Depends
from opscanvas_api.settings import Settings, get_settings

router = APIRouter()
SettingsDependency = Annotated[Settings, Depends(get_settings)]


class HealthResponse(TypedDict):
    status: str
    service: str
    version: str


@router.get("/healthz")
def healthz(settings: SettingsDependency) -> HealthResponse:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.version,
    }
