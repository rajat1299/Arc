from datetime import datetime
from decimal import Decimal
from math import ceil
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from opscanvas_api.store import RunStore
from opscanvas_core.events import Run, RunStatus, Span, SpanKind
from opscanvas_core.pricing import compute_cost
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/v1/runs", tags=["runs"])

_OPENAI_AGENTS_RUNTIMES = frozenset({"openai-agents", "opscanvas-agents", "openai_agents"})
_USD_QUANTUM = Decimal("0.0000000001")


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


class RunMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_count: int
    failed_count: int
    running_count: int
    suboptimal_count: int
    total_cost_usd: float
    total_tokens: int
    p95_latency_ms: int | None


def get_run_store(request: Request) -> RunStore:
    return cast(RunStore, request.app.state.run_store)


def _summary_from_run(run: Run) -> RunSummary:
    cost_usd = _effective_cost_usd(run)
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
        cost_usd=float(cost_usd) if cost_usd is not None else None,
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


def _p95_latency_ms(runs: list[Run]) -> int | None:
    latencies_ms = sorted(
        int((run.ended_at - run.started_at).total_seconds() * 1000)
        for run in runs
        if run.ended_at is not None
    )
    if not latencies_ms:
        return None

    index = ceil(0.95 * len(latencies_ms)) - 1
    return latencies_ms[index]


def _effective_cost_usd(run: Run) -> Decimal | None:
    if run.usage is not None and run.usage.cost_usd is not None:
        return _decimal_usd(run.usage.cost_usd)
    return _computed_run_cost_usd(run)


def _computed_run_cost_usd(run: Run) -> Decimal | None:
    total = Decimal("0")
    span_cost_found = False
    for span in run.spans:
        span_cost = _span_cost_usd(run, span)
        if span_cost is None:
            continue
        span_cost_found = True
        total += span_cost

    if span_cost_found:
        return total.quantize(_USD_QUANTUM)

    provider = _metadata_string(run, "provider")
    model = _metadata_string(run, "model")
    if provider is None or model is None:
        return None

    cost = compute_cost(run.usage, model=model, provider=provider)
    return cost.total_cost_usd if cost is not None else None


def _span_cost_usd(run: Run, span: Span) -> Decimal | None:
    if span.kind != SpanKind.model_call:
        return None

    provider = _span_provider(run, span)
    model = _span_model(span)
    if provider is None or model is None:
        return None

    cost = compute_cost(span.usage, model=model, provider=provider)
    return cost.total_cost_usd if cost is not None else None


def _span_provider(run: Run, span: Span) -> str | None:
    provider = _attribute_string(span, "provider")
    if provider is not None:
        return provider

    if run.runtime.lower() in _OPENAI_AGENTS_RUNTIMES:
        return "openai"
    return None


def _span_model(span: Span) -> str | None:
    return _attribute_string(span, "model") or _attribute_string(span, "agent.model")


def _attribute_string(span: Span, key: str) -> str | None:
    value = span.attributes.get(key)
    return value if isinstance(value, str) and value else None


def _metadata_string(run: Run, key: str) -> str | None:
    value = run.metadata.get(key)
    return value if isinstance(value, str) and value else None


def _decimal_usd(value: float) -> Decimal:
    return Decimal(str(value)).quantize(_USD_QUANTUM)


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


@router.get("/metrics", response_model=RunMetrics)
def get_run_metrics(
    run_store: Annotated[RunStore, Depends(get_run_store)],
) -> RunMetrics:
    runs = run_store.list()
    return RunMetrics(
        run_count=len(runs),
        failed_count=sum(1 for run in runs if run.status == RunStatus.failed),
        running_count=sum(1 for run in runs if run.status == RunStatus.running),
        suboptimal_count=sum(1 for run in runs if run.status == RunStatus.suboptimal),
        total_cost_usd=float(
            sum(
                ((_effective_cost_usd(run) or Decimal("0")) for run in runs),
                Decimal("0"),
            ).quantize(_USD_QUANTUM)
        ),
        total_tokens=sum(
            run.usage.total_tokens
            for run in runs
            if run.usage is not None and run.usage.total_tokens is not None
        ),
        p95_latency_ms=_p95_latency_ms(runs),
    )


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
