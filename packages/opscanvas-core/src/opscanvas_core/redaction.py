"""Minimal regex redaction helpers.

This module intentionally provides only a basic convenience redactor for early
internal contracts. It is not a final compliance-grade redaction system and must
not be treated as exhaustive PII detection.
"""

import re
from collections.abc import Mapping, Sequence

type RedactableScalar = str | int | float | bool | None
type RedactableValue = RedactableScalar | Mapping[str, RedactableValue] | Sequence[RedactableValue]

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
US_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"
)

EMAIL_REDACTION = "[REDACTED_EMAIL]"
PHONE_REDACTION = "[REDACTED_PHONE]"


def redact_basic_pii(value: RedactableValue) -> RedactableValue:
    """Redact emails and US phone numbers in strings, dicts, and lists.

    This is a deliberately small regex-based helper, not a compliance-grade
    redactor. It recurses through nested mappings and sequences while preserving
    non-string scalar values unchanged.
    """
    if isinstance(value, str):
        without_emails = EMAIL_RE.sub(EMAIL_REDACTION, value)
        return US_PHONE_RE.sub(PHONE_REDACTION, without_emails)
    if isinstance(value, Mapping):
        return {key: redact_basic_pii(nested_value) for key, nested_value in value.items()}
    if isinstance(value, Sequence):
        return [redact_basic_pii(nested_value) for nested_value in value]
    return value
