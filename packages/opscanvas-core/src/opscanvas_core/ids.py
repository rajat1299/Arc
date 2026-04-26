"""ID helpers for canonical OpsCanvas contract objects."""

from uuid import uuid4


def generate_prefixed_id(prefix: str) -> str:
    """Return a lowercase UUID4-based ID with the given contract prefix."""
    normalized_prefix = prefix.rstrip("_")
    if not normalized_prefix:
        raise ValueError("ID prefix must not be empty")
    return f"{normalized_prefix}_{uuid4().hex}"


def generate_run_id() -> str:
    """Return a generated run ID."""
    return generate_prefixed_id("run")


def generate_span_id() -> str:
    """Return a generated span ID."""
    return generate_prefixed_id("span")


def generate_event_id() -> str:
    """Return a generated span event ID."""
    return generate_prefixed_id("event")
