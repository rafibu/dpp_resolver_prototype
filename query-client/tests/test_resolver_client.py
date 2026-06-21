import httpx
import pytest

from query_client.config import Config
from query_client.resolver_client import ResolverError, get_platforms


def _client_returning(payload, status_code=200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_derives_base_url_from_resolution_url():
    payload = [
        {
            "platform": "platform-a",
            "issuer_id": "issuerA",
            "resolution_url": "http://platform-a:8081/dpps/{dppId}",
            "subject_types": ["battery"],
        }
    ]
    async with _client_returning(payload) as client:
        platforms = await get_platforms(client, Config())
    assert len(platforms) == 1
    assert platforms[0].platform_id == "platform-a"
    assert platforms[0].base_url == "http://platform-a:8081"


@pytest.mark.asyncio
async def test_deduplicates_platforms_shared_across_issuers():
    payload = [
        {
            "platform": "platform-a",
            "issuer_id": "issuerA",
            "resolution_url": "http://platform-a:8081/dpps/{dppId}",
        },
        {
            "platform": "platform-a",
            "issuer_id": "issuerB",
            "resolution_url": "http://platform-a:8081/dpps/{dppId}",
        },
        {
            "platform": "platform-b",
            "issuer_id": "issuerC",
            "resolution_url": "http://platform-b:8082/dpps/{dppId}",
        },
    ]
    async with _client_returning(payload) as client:
        platforms = await get_platforms(client, Config())
    assert {p.base_url for p in platforms} == {
        "http://platform-a:8081",
        "http://platform-b:8082",
    }
    assert len(platforms) == 2


@pytest.mark.asyncio
async def test_explicit_base_url_takes_precedence():
    payload = [{"platform_id": "p1", "base_url": "http://p1:9000/"}]
    async with _client_returning(payload) as client:
        platforms = await get_platforms(client, Config())
    assert platforms[0].base_url == "http://p1:9000"


@pytest.mark.asyncio
async def test_malformed_entries_are_skipped():
    payload = [
        {"issuer_id": "no-url"},
        {"platform": "p1", "resolution_url": "http://p1:8081/dpps/{dppId}"},
    ]
    async with _client_returning(payload) as client:
        platforms = await get_platforms(client, Config())
    assert len(platforms) == 1
    assert platforms[0].base_url == "http://p1:8081"


@pytest.mark.asyncio
async def test_http_error_raises_resolver_error():
    async with _client_returning({}, status_code=500) as client:
        with pytest.raises(ResolverError):
            await get_platforms(client, Config())
