from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import HTTPException
from opscanvas_api.auth import (
    ApiKeyPrincipal,
    authenticate_api_key,
    configured_api_keys,
    require_api_key,
    validate_api_key,
)
from opscanvas_api.settings import Settings


def fake_settings(*, auth_enabled: bool, api_keys: str) -> Settings:
    return cast(
        Settings,
        SimpleNamespace(auth_enabled=auth_enabled, api_keys=api_keys),
    )


def test_configured_api_keys_splits_commas_newlines_and_ignores_blanks() -> None:
    settings = fake_settings(
        auth_enabled=True,
        api_keys=" first-key, second-key\n\n third-key \n, ",
    )

    assert configured_api_keys(settings) == ("first-key", "second-key", "third-key")


def test_validate_api_key_accepts_only_configured_key() -> None:
    configured_keys = ("alpha", "beta")

    assert validate_api_key("beta", configured_keys) is True
    assert validate_api_key("missing", configured_keys) is False
    assert validate_api_key("", configured_keys) is False


def test_authenticate_api_key_returns_non_secret_principal_for_valid_token() -> None:
    settings = fake_settings(auth_enabled=True, api_keys="alpha,beta")

    principal = authenticate_api_key("beta", settings)

    assert isinstance(principal, ApiKeyPrincipal)
    assert principal.key_id
    assert principal.key_id != "beta"
    assert "beta" not in principal.key_id


def test_authenticate_api_key_returns_none_for_invalid_token() -> None:
    settings = fake_settings(auth_enabled=True, api_keys="alpha,beta")

    assert authenticate_api_key("missing", settings) is None


def test_require_api_key_returns_none_when_auth_is_disabled() -> None:
    settings = fake_settings(auth_enabled=False, api_keys="")

    assert require_api_key(settings=settings, authorization=None) is None


def test_require_api_key_returns_principal_for_valid_bearer_token() -> None:
    settings = fake_settings(auth_enabled=True, api_keys="alpha,beta")

    principal = require_api_key(settings=settings, authorization="Bearer beta")

    assert isinstance(principal, ApiKeyPrincipal)
    expected = authenticate_api_key("beta", settings)
    assert expected is not None
    assert principal.key_id == expected.key_id


def test_require_api_key_rejects_missing_bearer_token() -> None:
    settings = fake_settings(auth_enabled=True, api_keys="alpha")

    with pytest.raises(HTTPException) as exc_info:
        require_api_key(settings=settings, authorization=None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


def test_require_api_key_rejects_malformed_scheme() -> None:
    settings = fake_settings(auth_enabled=True, api_keys="alpha")

    with pytest.raises(HTTPException) as exc_info:
        require_api_key(settings=settings, authorization="Basic alpha")

    assert exc_info.value.status_code == 401
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


def test_require_api_key_rejects_invalid_token_without_echoing_secret() -> None:
    settings = fake_settings(auth_enabled=True, api_keys="alpha")

    with pytest.raises(HTTPException) as exc_info:
        require_api_key(settings=settings, authorization="Bearer wrong-secret")

    assert exc_info.value.status_code == 401
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}
    assert "wrong-secret" not in str(exc_info.value.detail)
    assert "alpha" not in str(exc_info.value.detail)


def test_require_api_key_fails_closed_when_enabled_without_configured_keys() -> None:
    settings = fake_settings(auth_enabled=True, api_keys=" \n, ")

    with pytest.raises(HTTPException) as exc_info:
        require_api_key(settings=settings, authorization="Bearer alpha")

    assert exc_info.value.status_code == 503
