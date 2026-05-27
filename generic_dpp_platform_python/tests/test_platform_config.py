import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_platform_config_returns_seeded_values(http_client: AsyncClient) -> None:
    response = await http_client.get("/admin/platform-config")
    assert response.status_code == 200
    body = response.json()
    assert body["platform_name"] == "Test Platform"
    assert body["issuer_id"] == "issuerA"
    assert body["base_url"] == "http://localhost:8082"
    assert body["resolver_base_url"] == "http://resolver:8080"


@pytest.mark.asyncio
async def test_put_platform_config_updates_fields(http_client: AsyncClient) -> None:
    response = await http_client.put(
        "/admin/platform-config",
        json={"platform_name": "Updated Platform", "issuer_id": "updated-issuer"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["platform_name"] == "Updated Platform"
    assert body["issuer_id"] == "updated-issuer"
    assert body["base_url"] == "http://localhost:8082"


@pytest.mark.asyncio
async def test_put_platform_config_partial_update_preserves_other_fields(http_client: AsyncClient) -> None:
    await http_client.put("/admin/platform-config", json={"platform_name": "Partial Update"})
    response = await http_client.get("/admin/platform-config")
    body = response.json()
    assert body["platform_name"] == "Partial Update"
    assert body["issuer_id"] == "issuerA"
