import os

import pytest
from fastapi.testclient import TestClient

from dpp_platform_factory.api.api import app, get_docker_client, get_schema_seed_service, get_platform_service, state, \
    spawn_lock, default_platform_ids
from dpp_platform_factory.core.platform_service import PlatformService
from dpp_platform_factory.core.schema_seed_service import SchemaSeedService
from tests.helpers.fake_docker import FakeDockerClient
from tests.helpers.fake_resolver import FakeResolverClient


@pytest.fixture
def fake_docker():
    return FakeDockerClient()

@pytest.fixture
def fake_resolver():
    return FakeResolverClient("http://fake-resolver:8080")

@pytest.fixture
def test_state():
    # Return the global state but cleared
    state.resolver = None
    state.platforms.clear()
    default_platform_ids.clear()
    return state

@pytest.fixture
def client(fake_docker, fake_resolver, test_state):
    os.environ["DPP_FACTORY_TESTING"] = "true"
    
    def get_fake_docker():
        return fake_docker

    def fake_resolver_factory(url):
        fake_resolver.resolver_url = url
        return fake_resolver

    def get_fake_platform_service():
        return PlatformService(
            test_state, 
            fake_docker, 
            spawn_lock, 
            default_platform_ids,
            resolver_client_factory=fake_resolver_factory
        )

    def get_fake_schema_seed_service():
        return SchemaSeedService(
            test_state,
            resolver_client_factory=fake_resolver_factory
        )

    app.dependency_overrides[get_docker_client] = get_fake_docker
    app.dependency_overrides[get_platform_service] = get_fake_platform_service
    app.dependency_overrides[get_schema_seed_service] = get_fake_schema_seed_service
    
    with TestClient(app) as c:
        yield c
    
    app.dependency_overrides.clear()
