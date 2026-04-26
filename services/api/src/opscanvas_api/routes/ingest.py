from typing import Literal

from fastapi import APIRouter, status
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
def ingest_run(run: Run) -> AcceptedRun:
    return AcceptedRun(
        status="accepted",
        run_id=run.id,
        schema_version=run.schema_version,
        span_count=len(run.spans),
        event_count=sum(len(span.events) for span in run.spans),
    )
