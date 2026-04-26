"""Schema version constants for persisted OpsCanvas contracts.

Upgrade strategy:
- Producers should emit ``CURRENT_SCHEMA_VERSION`` for new persisted payloads.
- Readers may accept any value in ``SUPPORTED_SCHEMA_VERSIONS``.
- Future schema changes must add a summary entry and an explicit migration or
  compatibility note before being added to ``SUPPORTED_SCHEMA_VERSIONS``.
"""

CURRENT_SCHEMA_VERSION = "0.1"

SCHEMA_VERSION_SUMMARIES: dict[str, str] = {
    "0.1": "Initial canonical run/span/event contract for runtime-agnostic ingestion.",
}

SUPPORTED_SCHEMA_VERSIONS = frozenset(SCHEMA_VERSION_SUMMARIES)
