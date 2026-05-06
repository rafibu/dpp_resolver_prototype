import pytest
from datetime import datetime
from dpp_platform_factory.core.state import PlatformStatus, ResolverRecord

def test_seed_schemas_all(client, test_state):
    # Setup
    test_state.resolver = ResolverRecord(
        container_id="r", db_container_id="rd", 
        external_url="http://res", internal_url="http://res-i",
        status=PlatformStatus.RUNNING, started_at=datetime.now()
    )
    
    # We use a real file system for this test if possible, 
    # but since we are refactored, SchemaSeedService reads from Path("seed-schemas")
    # In tests, it might need to be adjusted.
    
    resp = client.post("/resolver/seed-schemas")
    assert resp.status_code == 200
    data = resp.json()
    assert "loaded" in data
    assert len(data["loaded"]) > 0
    assert "battery-1.0.json" in data["loaded"]

def test_seed_schemas_selected(client, test_state):
    test_state.resolver = ResolverRecord(
        container_id="r", db_container_id="rd", 
        external_url="http://res", internal_url="http://res-i",
        status=PlatformStatus.RUNNING, started_at=datetime.now()
    )
    
    resp = client.post("/resolver/seed-schemas", json={
        "schemas": ["battery-1.0.json"]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["loaded"] == ["battery-1.0.json"]

def test_seed_schemas_missing_resolver(client, test_state):
    test_state.resolver = None
    resp = client.post("/resolver/seed-schemas")
    assert resp.status_code == 503
