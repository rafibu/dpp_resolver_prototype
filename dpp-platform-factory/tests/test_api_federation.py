import pytest
from datetime import datetime

from dpp_platform_factory.core.state import PlatformStatus, PlatformRecord, ResolverRecord


def test_get_federation_empty(client, test_state):
    test_state.resolver = None
    resp = client.get("/federation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolver"] is None
    assert data["platforms"] == []

def test_get_federation_populated(client, test_state):
    test_state.resolver = ResolverRecord(
        container_id="r", db_container_id="rd", 
        external_url="http://res", internal_url="http://res-i",
        status=PlatformStatus.RUNNING, started_at=datetime.now()
    )
    test_state.platforms["p1"] = PlatformRecord(
        platform_id="p1", stack="s", issuer_id="i", subject_types=[],
        container_id="c", db_container_id="d",
        external_url="u", internal_url="i",
        status=PlatformStatus.RUNNING, created_at=datetime.now()
    )
    
    resp = client.get("/federation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolver"]["external_url"] == "http://res"
    assert data["resolver"]["internal_url"] == "http://res-i"
    assert len(data["platforms"]) == 1
    assert data["platforms"][0]["platform_id"] == "p1"

def test_list_platforms(client, test_state):
    test_state.platforms["p1"] = PlatformRecord(
        platform_id="p1", stack="s", issuer_id="i", subject_types=[],
        container_id="c", db_container_id="d",
        external_url="u", internal_url="i",
        status=PlatformStatus.RUNNING, created_at=datetime.now()
    )
    resp = client.get("/platforms")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
