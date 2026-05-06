import pytest
from workload.federation import FederationClient, PlatformStatus

@pytest.mark.asyncio
async def test_discover_success(httpx_mock):
    factory_url = "http://factory:8000"
    mock_response = {
        "resolver": {
            "external_url": "http://resolver:8081",
            "status": "RUNNING"
        },
        "platforms": [
            {
                "platform_id": "platform-a",
                "stack": "java",
                "issuer_id": "issuerA",
                "subject_types": ["pv_module"],
                "external_url": "http://platform-a:8082",
                "status": "RUNNING",
                "created_at": "2026-05-03T12:00:00Z"
            }
        ]
    }
    httpx_mock.add_response(url=f"{factory_url}/federation", json=mock_response)

    async with FederationClient() as client:
        overview = await client.discover(factory_url)
        assert overview.resolver.external_url == "http://resolver:8081"
        assert len(overview.platforms) == 1
        assert overview.platforms[0].platform_id == "platform-a"
        
        # Test caching
        overview2 = await client.discover(factory_url)
        assert overview2 is overview

        # Test helper methods
        assert await client.resolver_url() == "http://resolver:8081"
        platforms = await client.all_platforms()
        assert len(platforms) == 1
        
        platform = await client.find_platform_for_subject_type("pv_module")
        assert platform.platform_id == "platform-a"

@pytest.mark.asyncio
async def test_find_platform_not_found(httpx_mock):
    factory_url = "http://factory:8000"
    mock_response = {"resolver": None, "platforms": []}
    httpx_mock.add_response(url=f"{factory_url}/federation", json=mock_response)

    async with FederationClient() as client:
        await client.discover(factory_url)
        with pytest.raises(ValueError, match="No platform found for subject type: unknown"):
            await client.find_platform_for_subject_type("unknown")

@pytest.mark.asyncio
async def test_resolver_url_missing(httpx_mock):
    factory_url = "http://factory:8000"
    mock_response = {"resolver": None, "platforms": []}
    httpx_mock.add_response(url=f"{factory_url}/federation", json=mock_response)

    async with FederationClient() as client:
        await client.discover(factory_url)
        with pytest.raises(RuntimeError, match="No resolver info available in federation"):
            await client.resolver_url()
