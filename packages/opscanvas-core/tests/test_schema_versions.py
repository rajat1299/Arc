from datetime import UTC, datetime

import pytest
from opscanvas_core.events import Run, RunStatus
from opscanvas_core.schema_versions import (
    CURRENT_SCHEMA_VERSION,
    SCHEMA_VERSION_SUMMARIES,
    SUPPORTED_SCHEMA_VERSIONS,
)
from pydantic import ValidationError


def test_current_schema_version_is_supported() -> None:
    assert CURRENT_SCHEMA_VERSION in SUPPORTED_SCHEMA_VERSIONS
    assert isinstance(SUPPORTED_SCHEMA_VERSIONS, frozenset)


def test_supported_schema_versions_have_non_empty_summaries() -> None:
    assert SUPPORTED_SCHEMA_VERSIONS
    assert set(SUPPORTED_SCHEMA_VERSIONS) == set(SCHEMA_VERSION_SUMMARIES)
    assert all(summary for summary in SCHEMA_VERSION_SUMMARIES.values())


def test_run_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValidationError):
        Run(
            id="run_123",
            schema_version="999.0",
            status=RunStatus.running,
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            runtime="pytest",
        )
