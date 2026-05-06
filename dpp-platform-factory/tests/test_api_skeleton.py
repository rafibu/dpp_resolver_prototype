import pytest
from dpp_platform_factory.api.api import app

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

def test_lifespan_testing_mode(client):
    # This just ensures the client (which triggers lifespan) works without error
    # when DPP_FACTORY_TESTING=true is set in conftest
    resp = client.get("/health")
    assert resp.status_code == 200
