"""Shared test helpers: a routing async mock transport and response builders.

Importable from sibling test modules because pytest's default (prepend) import
mode puts the tests directory on ``sys.path``.
"""

from __future__ import annotations

import asyncio
import httpx
import json
from query_client.config import Config
from query_client.service import FederatedQueryService
from typing import Any, Awaitable, Callable

Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]

DEFAULT_PLATFORMS = [
    {"platform": "platform-a", "issuer_id": "A", "resolution_url": "http://platform-a:8081/dpps/{dppId}"},
    {"platform": "platform-b", "issuer_id": "B", "resolution_url": "http://platform-b:8082/dpps/{dppId}"},
]


class RoutingTransport(httpx.AsyncBaseTransport):
    """Routes requests to per-key handlers and records every request seen.

    The resolver request (path ``/admin/platforms``) maps to key ``"resolver"``;
    every other request maps to its URL host (e.g. ``"platform-a"``).
    """

    def __init__(self, handlers: dict[str, Handler]) -> None:
        self._handlers = handlers
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = "resolver" if request.url.path == "/admin/platforms" else request.url.host
        handler = self._handlers.get(key)
        if handler is None:
            return httpx.Response(404, json={"error": f"no handler for {key}"})
        return await handler(request)

    def platform_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path != "/admin/platforms"]

    def body_for(self, host: str) -> dict[str, Any]:
        for request in self.requests:
            if request.url.host == host and request.url.path != "/admin/platforms":
                return json.loads(request.content.decode("utf-8"))
        raise AssertionError(f"no platform request recorded for host {host!r}")


def resolver_handler(platforms: list[dict] | None = None, *, status: int = 200) -> Handler:
    payload = DEFAULT_PLATFORMS if platforms is None else platforms

    async def _h(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return _h


def json_handler(payload: Any, *, status: int = 200, delay: float = 0.0) -> Handler:
    async def _h(_req: httpx.Request) -> httpx.Response:
        if delay:
            await asyncio.sleep(delay)
        return httpx.Response(status, json=payload)

    return _h


def error_handler(exc: Exception) -> Handler:
    async def _h(_req: httpx.Request) -> httpx.Response:
        raise exc

    return _h


def select_payload(platform_id: str, matches: list[Any]) -> dict[str, Any]:
    return {
        "result_mode": "SELECT",
        "execution_mode": "INDEXED",
        "platform_id": platform_id,
        "matches": matches,
    }


def count_payload(platform_id: str, count: int) -> dict[str, Any]:
    return {
        "result_mode": "COUNT",
        "execution_mode": "INDEXED",
        "platform_id": platform_id,
        "count": count,
    }


def sum_payload(platform_id: str, aggregate) -> dict[str, Any]:
    return {
        "result_mode": "SUM",
        "execution_mode": "INDEXED",
        "platform_id": platform_id,
        "aggregate": aggregate,
    }


def make_transport(handlers: dict[str, Handler]) -> RoutingTransport:
    return RoutingTransport(handlers)


def make_service(transport: RoutingTransport, config: Config | None = None) -> FederatedQueryService:
    client = httpx.AsyncClient(transport=transport)
    return FederatedQueryService(
        config=config or Config(resolver_base_url="http://localhost:8080"),
        http_client=client,
    )
