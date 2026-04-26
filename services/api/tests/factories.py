from typing import Any

from opscanvas_core.schema_versions import CURRENT_SCHEMA_VERSION


def canonical_run_payload(**overrides: Any) -> dict[str, Any]:
    run_id = overrides.pop("id", "run_123")
    span_id = overrides.pop("span_id", f"span_{run_id}")
    event_id = overrides.pop("event_id", f"evt_{run_id}")
    payload: dict[str, Any] = {
        "id": run_id,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "status": "succeeded",
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:03Z",
        "runtime": "pytest",
        "project_id": "project_123",
        "environment": "test",
        "tenant_id": "tenant_123",
        "workflow_name": "contract-test",
        "usage": {"total_tokens": 18, "cost_usd": 0.02},
        "metadata": {"trace": "abc"},
        "spans": [
            {
                "id": span_id,
                "run_id": run_id,
                "kind": "tool_call",
                "name": "search",
                "started_at": "2026-01-01T00:00:01Z",
                "ended_at": "2026-01-01T00:00:02Z",
                "input": {"query": "contract"},
                "output": {"count": 1},
                "events": [
                    {
                        "id": event_id,
                        "span_id": span_id,
                        "name": "tool.completed",
                        "timestamp": "2026-01-01T00:00:02Z",
                        "attributes": {"ok": True},
                    }
                ],
            }
        ],
    }
    payload.update(overrides)
    return payload
