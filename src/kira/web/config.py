"""Web server configuration."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Sentinel value used to detect when no JWT secret was explicitly configured.
_INSECURE_DEFAULT_SECRET = "kira-kanban-dev-secret-not-for-production-use"


@dataclass
class WebConfig:
    """Configuration for the web server."""

    host: str = "0.0.0.0"
    port: int = 8000
    db_path: str = ".kira/kanban.db"
    chromadb_path: str = ".kira/chromadb"
    jwt_secret: str = _INSECURE_DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    cors_origins: list[str] | None = None
    debug: bool = False
    auth_mode: str = "mock"  # "mock" or "centauth"
    centauth_url: str = ""
    centauth_app_name: str = "kira"
    centauth_verify_ssl: bool = True

    @classmethod
    def load(cls) -> WebConfig:
        config = cls()
        config.host = os.environ.get("KIRA_HOST", config.host)
        config.port = int(os.environ.get("KIRA_PORT", config.port))
        config.db_path = os.environ.get("KIRA_DB_PATH", config.db_path)
        config.chromadb_path = os.environ.get("KIRA_CHROMADB_PATH", config.chromadb_path)
        config.jwt_secret = os.environ.get("KIRA_JWT_SECRET", "")
        config.debug = os.environ.get("KIRA_DEBUG", "").lower() in ("1", "true")
        origins = os.environ.get("KIRA_CORS_ORIGINS")
        if origins:
            config.cors_origins = [o.strip() for o in origins.split(",")]
        config.auth_mode = os.environ.get("KIRA_AUTH_MODE", config.auth_mode)
        config.centauth_url = os.environ.get("KIRA_CENTAUTH_URL", config.centauth_url)
        config.centauth_app_name = os.environ.get(
            "KIRA_CENTAUTH_APP_NAME", config.centauth_app_name
        )
        config.centauth_verify_ssl = os.environ.get(
            "KIRA_CENTAUTH_VERIFY_SSL", "true"
        ).lower() not in ("0", "false", "no")

        # Fail-closed: refuse to start with an insecure JWT secret in production auth mode.
        if not config.jwt_secret or config.jwt_secret == _INSECURE_DEFAULT_SECRET:
            if config.auth_mode != "mock":
                raise RuntimeError(
                    "KIRA_JWT_SECRET must be set to a strong random value when "
                    "auth_mode is not 'mock'. Generate one with: "
                    "python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            # In mock/dev mode, generate a random secret per-process to avoid using
            # the well-known default. Sessions won't survive restarts, which is fine
            # for local development.
            config.jwt_secret = secrets.token_hex(32)
            logger.warning(
                "KIRA_JWT_SECRET not set -- using random ephemeral secret. "
                "Set KIRA_JWT_SECRET for persistent sessions."
            )

        return config
