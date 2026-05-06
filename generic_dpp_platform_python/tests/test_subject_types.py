import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_all_subject_types_initially_empty(http_client: AsyncClient) -> None:
    response = await http_client.get("/admin/subject-types")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_subject_type_happy_path(http_client: AsyncClient) -> None:
    response = await http_client.post(
        "/admin/subject-types",
        json={"name": "pv_module", "description": "Photovoltaic module"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "pv_module"
    assert body["description"] == "Photovoltaic module"

    list_response = await http_client.get("/admin/subject-types")
    assert list_response.status_code == 200
    items = list_response.json()
    assert len(items) == 1
    assert items[0]["name"] == "pv_module"


@pytest.mark.asyncio
async def test_create_subject_type_duplicate_name_returns_400(http_client: AsyncClient) -> None:
    payload = {"name": "battery", "description": "Battery pack"}
    first = await http_client.post("/admin/subject-types", json=payload)
    assert first.status_code == 201

    second = await http_client.post("/admin/subject-types", json=payload)
    assert second.status_code == 400
    assert "battery" in second.json()["detail"]


@pytest.mark.asyncio
async def test_create_subject_type_missing_name_returns_422(http_client: AsyncClient) -> None:
    response = await http_client.post("/admin/subject-types", json={"description": "no name"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_multiple_subject_types(http_client: AsyncClient) -> None:
    for name in ["pv_module", "battery", "inverter"]:
        response = await http_client.post("/admin/subject-types", json={"name": name})
        assert response.status_code == 201

    list_response = await http_client.get("/admin/subject-types")
    names = {item["name"] for item in list_response.json()}
    assert names == {"pv_module", "battery", "inverter"}
