"""Schema version constants for persisted OpsCanvas contracts."""

CURRENT_SCHEMA_VERSION = "0.1"

SCHEMA_VERSION_SUMMARIES: dict[str, str] = {
    "0.1": "Initial canonical run/span/event contract for runtime-agnostic ingestion.",
}

SUPPORTED_SCHEMA_VERSIONS = tuple(SCHEMA_VERSION_SUMMARIES)
