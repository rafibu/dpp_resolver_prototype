import pytest
from datetime import datetime
from dpp_platform_factory.core.state import PlatformStatus, PlatformRecord

def test_delete_platform_success(client, fake_docker, test_state):
    # Setup: Existing dynamic platform
    record = PlatformRecord(
        platform_id="platform-c",
        stack="spring-postgres",
        issuer_id="issuer-1",
        subject_types=["a"],
        container_id="id-dpp-platform-c",
        db_container_id="id-dpp-platform-c-db",
        external_url="http://localhost:8084",
        internal_url="http://dpp-platform-c:8080",
        status=PlatformStatus.RUNNING,
        created_at=datetime.now()
    )
    test_state.platforms["platform-c"] = record
    fake_docker.containers_list["dpp-platform-c"] = fake_docker.run_container(None, "dpp-platform-c", {}, {}, {}, "", {})
    fake_docker.containers_list["dpp-platform-c-db"] = fake_docker.run_container(None, "dpp-platform-c-db", {}, {}, {}, "", {})

    resp = client.delete("/platforms/platform-c")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}
    
    assert "platform-c" not in test_state.platforms
    assert "dpp-platform-c" not in fake_docker.containers_list
    assert "dpp-platform-c-db" not in fake_docker.containers_list

def test_delete_default_forbidden(client, test_state):
    from dpp_platform_factory.api.api import default_platform_ids
    default_platform_ids.add("platform-a")
    
    test_state.platforms["platform-a"] = PlatformRecord(
        platform_id="platform-a",
        stack="spring-postgres", issuer_id="i", subject_types=[],
        container_id="c", db_container_id="d",
        external_url="u", internal_url="i",
        status=PlatformStatus.RUNNING, created_at=datetime.now()
    )

    resp = client.delete("/platforms/platform-a")
    assert resp.status_code == 403
    assert "Default platforms cannot be deleted" in resp.json()["detail"]

def test_delete_missing(client):
    resp = client.delete("/platforms/missing")
    assert resp.status_code == 404
