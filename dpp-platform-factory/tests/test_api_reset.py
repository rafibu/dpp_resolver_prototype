import pytest
from datetime import datetime
from dpp_platform_factory.core.state import PlatformStatus, PlatformRecord, ResolverRecord

def test_reset_platform_success(client, fake_docker, fake_resolver, test_state):
    # Setup
    test_state.resolver = ResolverRecord(
        container_id="r", db_container_id="rd", 
        external_url="http://res", internal_url="http://res-i",
        status=PlatformStatus.RUNNING, started_at=datetime.now()
    )
    record = PlatformRecord(
        platform_id="platform-c",
        stack="spring-postgres", issuer_id="i", subject_types=[],
        container_id="id-dpp-platform-c", db_container_id="id-dpp-platform-c-db",
        external_url="http://localhost:8084", internal_url="i",
        status=PlatformStatus.RUNNING, created_at=datetime.now()
    )
    test_state.platforms["platform-c"] = record
    fake_docker.containers_list["dpp-platform-c"] = fake_docker.run_container(None, "dpp-platform-c", {}, {}, {}, "", {})
    fake_docker.containers_list["dpp-platform-c-db"] = fake_docker.run_container(None, "dpp-platform-c-db", {}, {}, {}, "", {})

    resp = client.post("/platforms/platform-c/reset")
    assert resp.status_code == 200
    assert resp.json()["status"] == "RUNNING"
    
    # DB container should have a new ID in our fake world (rebuild_db logic)
    # Our rebuild_db in platform.py calls client.run_container which generates id-dpp-platform-c-db
    # wait, rebuild_db generates new container name or same name?
    # In platform.py: db_name = f"dpp-{record.platform_id}-db"
    # It removes old one and creates new one with same name.
    assert "dpp-platform-c-db" in fake_docker.containers_list

def test_reset_paused_conflict(client, test_state):
    test_state.platforms["platform-c"] = PlatformRecord(
        platform_id="platform-c",
        stack="spring-postgres", issuer_id="i", subject_types=[],
        container_id="c", db_container_id="d",
        external_url="u", internal_url="i",
        status=PlatformStatus.PAUSED, created_at=datetime.now()
    )
    resp = client.post("/platforms/platform-c/reset")
    assert resp.status_code == 409
