from threading import RLock
from typing import Protocol

from opscanvas_core.events import Run, RunStatus


class RunStore(Protocol):
    def upsert(self, run: Run) -> None:
        """Store a canonical run, replacing any previous run with the same ID."""

    def get(self, run_id: str) -> Run | None:
        """Return a canonical run by ID."""

    def list(
        self,
        *,
        status: RunStatus | None = None,
        runtime: str | None = None,
        tenant_id: str | None = None,
        environment: str | None = None,
        limit: int | None = None,
    ) -> list[Run]:
        """Return canonical runs sorted by newest start time first."""


class InMemoryRunStore:
    """Process-local run store for local/dev ingestion and query loops."""

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._lock = RLock()

    def upsert(self, run: Run) -> None:
        with self._lock:
            self._runs[run.id] = run.model_copy(deep=True)

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            return run.model_copy(deep=True)

    def list(
        self,
        *,
        status: RunStatus | None = None,
        runtime: str | None = None,
        tenant_id: str | None = None,
        environment: str | None = None,
        limit: int | None = None,
    ) -> list[Run]:
        with self._lock:
            runs = list(self._runs.values())

        filtered = [
            run
            for run in runs
            if (status is None or run.status == status)
            and (runtime is None or run.runtime == runtime)
            and (tenant_id is None or run.tenant_id == tenant_id)
            and (environment is None or run.environment == environment)
        ]
        sorted_runs = sorted(filtered, key=lambda run: run.started_at, reverse=True)
        limited_runs = sorted_runs[:limit] if limit is not None else sorted_runs
        return [run.model_copy(deep=True) for run in limited_runs]
