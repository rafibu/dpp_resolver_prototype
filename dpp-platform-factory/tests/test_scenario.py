import pytest
from datetime import datetime
from dpp_platform_factory.core.state import PlatformStatus, ResolverRecord

def test_scenario_spawn_and_seed(client, fake_docker, fake_resolver, test_state):
    # 1. Resolver starts up (simulated)
    test_state.resolver = ResolverRecord(
        container_id="res-id",
        db_container_id="res-db-id",
        external_url="http://resolver:8080",
        internal_url="http://resolver-internal:8080",
        status=PlatformStatus.RUNNING,
        started_at=datetime.now()
    )

    # 2. Seed schemas
    resp = client.post("/resolver/seed-schemas")
    assert resp.status_code == 200
    assert "battery-1.0.json" in resp.json()["loaded"]
    assert len(fake_resolver.schemas) > 0

    # 3. Spawn a new platform
    resp = client.post("/platforms", json={
        "stack": "spring-postgres",
        "issuer_id": "issuer-X",
        "subject_types": ["battery"]
    })
    assert resp.status_code == 200
    platform_id = resp.json()["platform_id"]
    
    # 4. Verify federation state
    resp = client.get("/federation")
    data = resp.json()
    assert data["resolver"]["status"] == "RUNNING"
    # Find our new platform
    p_info = next(p for p in data["platforms"] if p["platform_id"] == platform_id)
    assert p_info["status"] == "RUNNING"
    assert p_info["issuer_id"] == "issuer-X"
    
    # 5. Verify it was registered with resolver
    assert platform_id in fake_resolver.platforms
    assert fake_resolver.platforms[platform_id]["issuerId"] == "issuer-X"
    
    # 6. Delete platform and check consistency
    del_resp = client.delete(f"/platforms/{platform_id}")
    assert del_resp.status_code == 200
    
    resp = client.get("/federation")
    assert resp.status_code == 200
    current_platforms = [p["platform_id"] for p in resp.json()["platforms"]]
    assert platform_id not in current_platforms
    # Note: Teardown requirement says "Do not unregister from Resolver"
    assert platform_id in fake_resolver.platforms
