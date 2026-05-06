import pytest
from datetime import datetime
from dpp_platform_factory.core.state import PlatformStatus, ResolverRecord

def test_spawn_platform_success(client, fake_docker, test_state):
    # Setup: Resolver must be ready
    test_state.resolver = ResolverRecord(
        container_id="res-id",
        db_container_id="res-db-id",
        external_url="http://resolver:8080",
        internal_url="http://resolver-internal:8080",
        status=PlatformStatus.RUNNING,
        started_at=datetime.now()
    )

    resp = client.post("/platforms", json={
        "stack": "spring-postgres",
        "issuer_id": "issuer-123",
        "subject_types": ["battery"]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["platform_id"] == "platform-a"
    assert data["stack"] == "spring-postgres"
    assert data["status"] == "RUNNING"
    
    # Verify fake docker state
    assert "dpp-platform-a" in fake_docker.containers_list
    assert "dpp-platform-a-db" in fake_docker.containers_list

def test_spawn_platform_invalid_stack(client):
    resp = client.post("/platforms", json={
        "stack": "invalid",
        "issuer_id": "issuer-123",
        "subject_types": ["battery"]
    })
    assert resp.status_code == 400
    assert "Unsupported stack" in resp.json()["detail"]

def test_spawn_platform_missing_resolver(client, test_state):
    test_state.resolver = None
    resp = client.post("/platforms", json={
        "stack": "spring-postgres",
        "issuer_id": "issuer-123",
        "subject_types": ["battery"]
    })
    assert resp.status_code == 503
    assert "Resolver not ready" in resp.json()["detail"]

def test_spawn_platform_rollback_on_failure(client, fake_docker, fake_resolver, test_state):
    # Setup: Resolver ready
    test_state.resolver = ResolverRecord(
        container_id="res-id",
        db_container_id="res-db-id",
        external_url="http://resolver:8080",
        internal_url="http://resolver-internal:8080",
        status=PlatformStatus.RUNNING,
        started_at=datetime.now()
    )
    
    # Force registration failure via fake resolver
    fake_resolver.fail_registration = True

    resp = client.post("/platforms", json={
        "stack": "spring-postgres",
        "issuer_id": "issuer-123",
        "subject_types": ["battery"]
    })
    assert resp.status_code == 503 
    
    # Verify cleanup: no platform-a containers should remain
    assert "dpp-platform-a" not in fake_docker.containers_list
    assert "dpp-platform-a-db" not in fake_docker.containers_list
    assert "platform-a" not in test_state.platforms
