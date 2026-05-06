import pytest
from datetime import datetime
from dpp_platform_factory.core.state import PlatformStatus, PlatformRecord, ResolverRecord

def test_spawn_docker_failure(client, fake_docker, test_state):
    test_state.resolver = ResolverRecord(
        container_id="r", db_container_id="rd", 
        external_url="http://res", internal_url="http://res-i",
        status=PlatformStatus.RUNNING, started_at=datetime.now()
    )
    # Force docker run failure
    fake_docker.fail_run_on = "dpp-platform-a-db"

    resp = client.post("/platforms", json={
        "stack": "spring-postgres",
        "issuer_id": "i",
        "subject_types": ["a"]
    })
    assert resp.status_code == 500
    assert "Simulated failure" in resp.json()["detail"]

def test_reset_db_rebuild_failure(client, fake_docker, test_state, mocker):
    # Setup
    record = PlatformRecord(
        platform_id="platform-c",
        stack="spring-postgres", issuer_id="i", subject_types=[],
        container_id="id-dpp-platform-c", db_container_id="id-dpp-platform-c-db",
        external_url="http://localhost:8084", internal_url="i",
        status=PlatformStatus.RUNNING, created_at=datetime.now()
    )
    test_state.platforms["platform-c"] = record
    fake_docker.containers_list["dpp-platform-c"] = fake_docker.run_container(None, "dpp-platform-c", {}, {}, {}, "", {})
    
    # Force rebuild_db failure
    mocker.patch("dpp_platform_factory.core.platform_service.rebuild_db", side_effect=Exception("DB rebuild failed"))

    resp = client.post("/platforms/platform-c/reset")
    assert resp.status_code == 500
    assert test_state.platforms["platform-c"].status == PlatformStatus.ERROR

def test_seed_schemas_partial_failure(client, fake_resolver, test_state):
    test_state.resolver = ResolverRecord(
        container_id="r", db_container_id="rd", 
        external_url="http://res", internal_url="http://res-i",
        status=PlatformStatus.RUNNING, started_at=datetime.now()
    )
    
    # Mock publish_schema to fail for one specific schema
    async def side_effect(subject_type, schema):
        if "battery" in subject_type.lower():
            raise Exception("Publish failed")
        return None
    
    fake_resolver.publish_schema = side_effect

    resp = client.post("/resolver/seed-schemas")
    assert resp.status_code == 200
    data = resp.json()
    assert "battery-1.0.json" in str(data["failed"])
    assert len(data["loaded"]) > 0
