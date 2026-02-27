"""Auth provider abstraction for dual-mode authentication."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
import jwt as pyjwt

logger = logging.getLogger(__name__)


@dataclass
class AuthResult:
    """Result from a successful authentication."""

    username: str
    display_name: str
    email: str = ""
    department: str = ""
    roles: list[str] = field(default_factory=list)
    access_token: str = ""
    refresh_token: str = ""
    external_sub: str = ""  # CentAuth subject ID


@dataclass
class TokenPair:
    """Refreshed token pair."""

    access_token: str
    refresh_token: str


class AuthProvider(Protocol):
    """Protocol for auth providers."""

    @property
    def mode(self) -> str: ...

    async def authenticate(self, username: str, password: str) -> AuthResult: ...

    async def refresh(self, refresh_token: str) -> TokenPair: ...

    async def validate_external_token(self, token: str) -> dict[str, Any] | None: ...


class MockAuthProvider:
    """Mock auth: username only, no real password check."""

    @property
    def mode(self) -> str:
        return "mock"

    async def authenticate(self, username: str, password: str) -> AuthResult:
        # Mock auth ignores password
        return AuthResult(
            username=username.strip().lower(),
            display_name=username.strip().capitalize(),
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        raise NotImplementedError("Mock auth does not support refresh tokens")

    async def validate_external_token(self, token: str) -> dict[str, Any] | None:
        return None


class CentAuthProvider:
    """CentAuth SSO provider — calls REST API directly via httpx."""

    def __init__(self, centauth_url: str, app_name: str, verify_ssl: bool = True):
        self._centauth_url = centauth_url.rstrip("/")
        self._app_name = app_name
        self._verify_ssl = verify_ssl

    @property
    def mode(self) -> str:
        return "centauth"

    def _decode_jwt_unverified(self, token: str) -> dict[str, Any]:
        """Decode a JWT without signature verification (trusted source)."""
        return pyjwt.decode(token, options={"verify_signature": False})

    async def authenticate(self, username: str, password: str) -> AuthResult:
        if not password:
            raise ValueError("Password is required for CentAuth authentication")

        url = f"{self._centauth_url}/auth_service/get_token"
        params: dict[str, str] = {"debug": "false"}
        if self._app_name:
            params["app_name"] = self._app_name

        async with httpx.AsyncClient(verify=self._verify_ssl) as client:
            resp = await client.post(
                url,
                params=params,
                data={
                    "username": username,
                    "password": password,
                    "password_is_encoded": "false",
                },
                headers={"Accept": "application/json"},
            )

        if resp.status_code != 200:
            detail = resp.text[:200] if resp.text else resp.reason_phrase
            raise ValueError(f"Authentication failed ({resp.status_code}): {detail}")

        body = resp.json()
        access_token = body.get("access_token", "")
        refresh_token = body.get("refresh_token", "")

        if not access_token:
            raise ValueError("Authentication failed: no access token returned")

        # Decode JWT payload to extract user info
        token_data = self._decode_jwt_unverified(access_token)

        # Extract app-specific roles
        roles = []
        if self._app_name:
            for role_entry in token_data.get("roles", []):
                if role_entry.get("app_name") == self._app_name:
                    roles.append(role_entry.get("role_name", ""))

        return AuthResult(
            username=token_data.get("username", username),
            display_name=token_data.get("full_name", username),
            email=token_data.get("email", ""),
            department=token_data.get("department", ""),
            roles=roles,
            access_token=access_token,
            refresh_token=refresh_token,
            external_sub=token_data.get("sub", ""),
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        url = f"{self._centauth_url}/auth_service/refresh_token"

        async with httpx.AsyncClient(verify=self._verify_ssl) as client:
            resp = await client.post(
                url,
                json={"refresh_token": refresh_token},
                headers={"Accept": "application/json"},
            )

        if resp.status_code != 200:
            raise ValueError("Token refresh failed")

        body = resp.json()
        new_access = body.get("access_token", "")
        if not new_access:
            raise ValueError("Token refresh failed: no access token returned")

        return TokenPair(
            access_token=new_access,
            refresh_token=body.get("refresh_token", refresh_token),
        )

    async def validate_external_token(self, token: str) -> dict[str, Any] | None:
        """Decode a CentAuth JWT without signature verification."""
        try:
            return self._decode_jwt_unverified(token)
        except Exception:
            logger.debug("External token validation failed", exc_info=True)
            return None
