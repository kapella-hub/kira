"""Auth service: provider management and JWT operations."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import jwt

from ..config import WebConfig
from .provider import AuthProvider, CentAuthProvider, MockAuthProvider

_config: WebConfig | None = None
_provider: AuthProvider | None = None


def _get_config() -> WebConfig:
    global _config
    if _config is None:
        _config = WebConfig.load()
    return _config


def init_provider(config: WebConfig | None = None) -> AuthProvider:
    """Initialize the auth provider based on config."""
    global _provider, _config
    if config:
        _config = config
    else:
        config = _get_config()
    _config = config

    if config.auth_mode == "centauth":
        _provider = CentAuthProvider(
            centauth_url=config.centauth_url,
            app_name=config.centauth_app_name,
            verify_ssl=config.centauth_verify_ssl,
        )
    else:
        _provider = MockAuthProvider()

    return _provider


def get_provider() -> AuthProvider:
    """Get the current auth provider. Initializes if needed."""
    global _provider
    if _provider is None:
        _provider = init_provider()
    return _provider


def create_token(user_id: str, username: str) -> str:
    """Create a JWT token for a user."""
    config = _get_config()
    payload = {
        "sub": user_id,
        "username": username,
        "exp": datetime.now(UTC) + timedelta(hours=config.jwt_expire_hours),
        "iat": datetime.now(UTC),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, config.jwt_secret, algorithm=config.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises jwt.InvalidTokenError on failure."""
    config = _get_config()
    return jwt.decode(token, config.jwt_secret, algorithms=[config.jwt_algorithm])
