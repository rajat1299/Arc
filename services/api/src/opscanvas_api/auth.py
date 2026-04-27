from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from opscanvas_api.settings import Settings, get_settings


@dataclass(frozen=True)
class ApiKeyPrincipal:
    """Authenticated API-key caller without exposing the original secret."""

    key_id: str


_KEY_ID_PREFIX_LENGTH = 12
_SPLIT_API_KEYS_PATTERN = re.compile(r"[,\n]")
_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


def configured_api_keys(settings: Settings) -> tuple[str, ...]:
    return tuple(
        key
        for part in _SPLIT_API_KEYS_PATTERN.split(settings.api_keys)
        if (key := part.strip())
    )


def validate_api_key(token: str, configured_keys: tuple[str, ...]) -> bool:
    token_bytes = token.encode("utf-8")
    valid = False
    for configured_key in configured_keys:
        valid = secrets.compare_digest(token_bytes, configured_key.encode("utf-8")) or valid
    return valid


def authenticate_api_key(token: str, settings: Settings) -> ApiKeyPrincipal | None:
    if not validate_api_key(token, configured_api_keys(settings)):
        return None
    return ApiKeyPrincipal(key_id=_key_id(token))


def require_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> ApiKeyPrincipal | None:
    if not settings.auth_enabled:
        return None

    configured_keys = configured_api_keys(settings)
    if not configured_keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key authentication is enabled but no API keys are configured.",
        )

    token = _bearer_token(authorization)
    if token is None:
        raise _unauthorized()

    principal = authenticate_api_key(token, settings)
    if principal is None:
        raise _unauthorized()
    return principal


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None

    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key credentials.",
        headers=_BEARER_CHALLENGE,
    )


def _key_id(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return digest[:_KEY_ID_PREFIX_LENGTH]
