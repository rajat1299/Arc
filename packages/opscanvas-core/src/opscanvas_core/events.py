"""Canonical OpsCanvas run/span/event contracts.

Use ``model_dump(mode="json", by_alias=True)`` or ``model_dump_json(by_alias=True)``
when serializing these models for ingestion so aliased JSON keys such as ``input``
and ``output`` are emitted.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from opscanvas_core.schema_versions import CURRENT_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS


class ContractModel(BaseModel):
    """Base model settings shared by canonical contract objects."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RunStatus(StrEnum):
    """Canonical status values for a run."""

    succeeded = "succeeded"
    failed = "failed"
    interrupted = "interrupted"
    suboptimal = "suboptimal"
    running = "running"


class SpanKind(StrEnum):
    """Canonical span kinds emitted by runtime plugins and ingestion paths."""

    agent = "agent"
    model_call = "model_call"
    tool_call = "tool_call"
    handoff = "handoff"
    guardrail = "guardrail"
    mcp_list = "mcp_list"
    sandbox_op = "sandbox_op"
    retry = "retry"
    custom = "custom"


class Usage(ContractModel):
    """Token and cost accounting attached to runs or spans."""

    input_tokens: int | None = Field(default=None, ge=0, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, strict=True)
    cached_input_tokens: int | None = Field(default=None, ge=0, strict=True)
    reasoning_tokens: int | None = Field(default=None, ge=0, strict=True)
    total_tokens: int | None = Field(default=None, ge=0, strict=True)
    cost_usd: float | None = Field(default=None, ge=0, strict=True)


class SpanEvent(ContractModel):
    """Point-in-time event associated with a span."""

    id: str
    span_id: str
    name: str
    timestamp: datetime
    attributes: dict[str, JsonValue] = Field(default_factory=dict)


class Span(ContractModel):
    """Canonical unit of work inside a run."""

    id: str
    run_id: str
    kind: SpanKind
    name: str
    parent_id: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    usage: Usage | None = None
    input_data: JsonValue = Field(default=None, alias="input")
    output_data: JsonValue = Field(default=None, alias="output")
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    events: list[SpanEvent] = Field(default_factory=list)


class Run(ContractModel):
    """Canonical runtime-agnostic run contract."""

    id: str
    schema_version: str = CURRENT_SCHEMA_VERSION
    status: RunStatus
    started_at: datetime
    ended_at: datetime | None = None
    runtime: str
    project_id: str | None = None
    environment: str | None = None
    tenant_id: str | None = None
    user_id: str | None = None
    workflow_name: str | None = None
    usage: Usage | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    spans: list[Span] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def schema_version_must_be_supported(cls, value: str) -> str:
        """Reject persisted payloads using an unsupported schema version."""
        if value not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"Unsupported schema version: {value}")
        return value
