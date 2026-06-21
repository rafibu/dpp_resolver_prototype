"""Runtime configuration for the federated query client.

Configuration is read from environment variables with sensible prototype
defaults. A small immutable dataclass is used instead of pydantic-settings to
avoid adding a dependency; ``get_config`` reads the environment on each call so
tests can override values via ``monkeypatch.setenv`` or by constructing a
``Config`` directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw


@dataclass(frozen=True)
class Config:
    """Configuration object for the query client.

    Attributes mirror the documented environment variables. ``timeout_ms`` on a
    request overrides :attr:`default_timeout_ms`; the HTTP connect/read timeouts
    bound a single platform call.
    """

    resolver_base_url: str = "http://localhost:8080"
    platform_query_path: str = "/query/predicate"
    platform_query_method: str = "POST"
    default_timeout_ms: int = 120_000
    http_connect_timeout_ms: int = 5_000
    http_read_timeout_ms: int = 120_000
    cors_allow_origins: tuple[str, ...] = ("*",)

    @property
    def resolver_platforms_url(self) -> str:
        """Absolute URL of the resolver's registered-platforms endpoint."""
        return f"{self.resolver_base_url.rstrip('/')}/admin/platforms"


def get_config() -> Config:
    """Build a :class:`Config` from the current process environment."""
    origins = _env_str("CORS_ALLOW_ORIGINS", "*")
    allow_origins = tuple(
        origin.strip() for origin in origins.split(",") if origin.strip()
    ) or ("*",)
    return Config(
        resolver_base_url=_env_str("RESOLVER_BASE_URL", "http://localhost:8080"),
        platform_query_path=_env_str("PLATFORM_QUERY_PATH", "/query/predicate"),
        platform_query_method=_env_str("PLATFORM_QUERY_METHOD", "POST").upper(),
        default_timeout_ms=_env_int("DEFAULT_TIMEOUT_MS", 120_000),
        http_connect_timeout_ms=_env_int("HTTP_CONNECT_TIMEOUT_MS", 5_000),
        http_read_timeout_ms=_env_int("HTTP_READ_TIMEOUT_MS", 120_000),
        cors_allow_origins=allow_origins,
    )
