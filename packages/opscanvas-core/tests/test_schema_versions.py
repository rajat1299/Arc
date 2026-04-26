from opscanvas_core.schema_versions import (
    CURRENT_SCHEMA_VERSION,
    SCHEMA_VERSION_SUMMARIES,
    SUPPORTED_SCHEMA_VERSIONS,
)


def test_current_schema_version_is_supported() -> None:
    assert CURRENT_SCHEMA_VERSION in SUPPORTED_SCHEMA_VERSIONS


def test_supported_schema_versions_have_non_empty_summaries() -> None:
    assert SUPPORTED_SCHEMA_VERSIONS
    assert set(SUPPORTED_SCHEMA_VERSIONS) == set(SCHEMA_VERSION_SUMMARIES)
    assert all(summary for summary in SCHEMA_VERSION_SUMMARIES.values())
