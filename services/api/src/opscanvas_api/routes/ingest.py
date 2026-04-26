from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from opscanvas_api.routes.runs import get_run_store
from opscanvas_api.store import RunStore
from opscanvas_core.events import Run
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/v1/ingest", tags=["ingest"])


class AcceptedRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted"]
    run_id: str
    schema_version: str
    span_count: int
    event_count: int


@router.post("/runs", response_model=AcceptedRun, status_code=status.HTTP_202_ACCEPTED)
def ingest_run(run: Run, run_store: Annotated[RunStore, Depends(get_run_store)]) -> AcceptedRun:
    run_store.upsert(run)
    return AcceptedRun(
        status="accepted",
        run_id=run.id,
        schema_version=run.schema_version,
        span_count=len(run.spans),
        event_count=sum(len(span.events) for span in run.spans),
    )
