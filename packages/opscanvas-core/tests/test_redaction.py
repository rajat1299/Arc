from opscanvas_core.redaction import redact_basic_pii


def test_redacts_email_and_us_phone_in_plain_text() -> None:
    text = "Email raj@example.com or call (312) 555-0199."

    assert redact_basic_pii(text) == "Email [REDACTED_EMAIL] or call [REDACTED_PHONE]."


def test_redacts_nested_dict_and_list_values() -> None:
    value = {
        "user": "raj@example.com",
        "items": ["safe", "312-555-0199", {"notes": "call 312.555.0199"}],
        "count": 3,
    }

    assert redact_basic_pii(value) == {
        "user": "[REDACTED_EMAIL]",
        "items": ["safe", "[REDACTED_PHONE]", {"notes": "call [REDACTED_PHONE]"}],
        "count": 3,
    }
