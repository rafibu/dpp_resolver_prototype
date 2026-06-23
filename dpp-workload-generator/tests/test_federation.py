import httpx
import pytest

from workload.federation import FederationClient, PLATFORM_CREATION_TIMEOUT_SECONDS


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


@pytest.mark.asyncio
async def test_create_platform_allows_factory_startup_time():
    class RecordingClient:
        timeout = None

        async def post(self, url, *, json, timeout):
            self.timeout = timeout
            return httpx.Response(
                200,
                json={
                    "platform_id": "platform-c",
                    "stack": json["stack"],
                    "issuer_id": json["issuer_id"],
                    "subject_types": json["subject_types"],
                    "external_url": "http://platform-c:8083",
                    "internal_url": "http://dpp-platform-c:8080",
                    "status": "RUNNING",
                    "created_at": "2026-06-23T18:00:00Z",
                },
                request=httpx.Request("POST", url),
            )

        async def aclose(self):
            pass

    async with FederationClient() as client:
        original_client = client._client
        recorder = RecordingClient()
        client._client = recorder
        await original_client.aclose()
        created = await client.create_platform(
            "http://factory:8000",
            stack="spring-postgres",
            issuer_id="issuerC",
            subject_types=["s1_inverter"],
        )

    assert created.platform_id == "platform-c"
    assert recorder.timeout == PLATFORM_CREATION_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_create_platform_preserves_factory_failure_detail():
    class FailingClient:
        async def post(self, url, *, json, timeout):
            return httpx.Response(
                500,
                json={"detail": "Docker memory pressure killed the container"},
                request=httpx.Request("POST", url),
            )

        async def aclose(self):
            pass

    async with FederationClient() as client:
        original_client = client._client
        client._client = FailingClient()
        await original_client.aclose()
        with pytest.raises(RuntimeError, match="Docker memory pressure"):
            await client.create_platform(
                "http://factory:8000",
                stack="spring-postgres",
                issuer_id="s4invertermanufacturer",
                subject_types=["inverter"],
            )
