from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from opscanvas_api.store import RunStore
from opscanvas_core.events import Run, RunStatus, Span
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/v1/runs", tags=["runs"])


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    schema_version: str
    status: RunStatus
    runtime: str
    started_at: datetime
    ended_at: datetime | None
    tenant_id: str | None
    environment: str | None
    workflow_name: str | None
    span_count: int
    event_count: int
    cost_usd: float | None
    total_tokens: int | None


def get_run_store(request: Request) -> RunStore:
    return cast(RunStore, request.app.state.run_store)


def _summary_from_run(run: Run) -> RunSummary:
    return RunSummary(
        id=run.id,
        schema_version=run.schema_version,
        status=run.status,
        runtime=run.runtime,
        started_at=run.started_at,
        ended_at=run.ended_at,
        tenant_id=run.tenant_id,
        environment=run.environment,
        workflow_name=run.workflow_name,
        span_count=len(run.spans),
        event_count=sum(len(span.events) for span in run.spans),
        cost_usd=run.usage.cost_usd if run.usage is not None else None,
        total_tokens=run.usage.total_tokens if run.usage is not None else None,
    )


def _get_run_or_404(run_store: RunStore, run_id: str) -> Run:
    run = run_store.get(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' was not found.",
        )
    return run


@router.get("", response_model=list[RunSummary])
def list_runs(
    run_store: Annotated[RunStore, Depends(get_run_store)],
    status_filter: Annotated[RunStatus | None, Query(alias="status")] = None,
    runtime: str | None = None,
    tenant_id: str | None = None,
    environment: str | None = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> list[RunSummary]:
    runs = run_store.list(
        status=status_filter,
        runtime=runtime,
        tenant_id=tenant_id,
        environment=environment,
        limit=limit,
    )
    return [_summary_from_run(run) for run in runs]


@router.get("/{run_id}", response_model=Run)
def get_run(
    run_store: Annotated[RunStore, Depends(get_run_store)],
    run_id: Annotated[str, Path(min_length=1)],
) -> Run:
    return _get_run_or_404(run_store, run_id)


@router.get("/{run_id}/spans", response_model=list[Span])
def get_run_spans(
    run_store: Annotated[RunStore, Depends(get_run_store)],
    run_id: Annotated[str, Path(min_length=1)],
) -> list[Span]:
    return _get_run_or_404(run_store, run_id).spans
