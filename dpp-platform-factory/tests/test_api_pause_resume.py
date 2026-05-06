import pytest
from datetime import datetime
from dpp_platform_factory.core.state import PlatformStatus, PlatformRecord

def test_pause_platform_success(client, fake_docker, test_state):
    # Setup
    record = PlatformRecord(
        platform_id="platform-c",
        stack="spring-postgres", issuer_id="i", subject_types=[],
        container_id="id-dpp-platform-c", db_container_id="d",
        external_url="u", internal_url="i",
        status=PlatformStatus.RUNNING, created_at=datetime.now()
    )
    test_state.platforms["platform-c"] = record
    fake_docker.containers_list["dpp-platform-c"] = fake_docker.run_container(None, "dpp-platform-c", {}, {}, {}, "", {})

    resp = client.post("/platforms/platform-c/pause")
    assert resp.status_code == 200
    assert resp.json()["status"] == "PAUSED"
    assert fake_docker.containers_list["dpp-platform-c"].status == "exited"

def test_resume_platform_success(client, fake_docker, test_state):
    # Setup
    record = PlatformRecord(
        platform_id="platform-c",
        stack="spring-postgres", issuer_id="i", subject_types=[],
        container_id="id-dpp-platform-c", db_container_id="d",
        external_url="http://localhost:8084", internal_url="i",
        status=PlatformStatus.PAUSED, created_at=datetime.now()
    )
    test_state.platforms["platform-c"] = record
    cont = fake_docker.run_container(None, "dpp-platform-c", {}, {}, {}, "", {})
    cont.status = "exited"
    fake_docker.containers_list["dpp-platform-c"] = cont

    resp = client.post("/platforms/platform-c/resume")
    assert resp.status_code == 200
    assert resp.json()["status"] == "RUNNING"
    assert fake_docker.containers_list["dpp-platform-c"].status == "running"

def test_resume_health_timeout(client, fake_docker, test_state):
    # Setup
    record = PlatformRecord(
        platform_id="platform-c",
        stack="spring-postgres", issuer_id="i", subject_types=[],
        container_id="id-dpp-platform-c", db_container_id="d",
        external_url="http://localhost:8084", internal_url="i",
        status=PlatformStatus.PAUSED, created_at=datetime.now()
    )
    test_state.platforms["platform-c"] = record
    cont = fake_docker.run_container(None, "dpp-platform-c", {}, {}, {}, "", {})
    cont.status = "exited"
    fake_docker.containers_list["dpp-platform-c"] = cont
    
    # Force health timeout
    fake_docker.fail_wait_healthy_on = "dpp-platform-c"

    resp = client.post("/platforms/platform-c/resume")
    assert resp.status_code == 504
    assert test_state.platforms["platform-c"].status == "ERROR"
