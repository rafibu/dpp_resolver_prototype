from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from dpp_platform_factory.utils.config import FederationConfig, StackType, load_config

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_PLATFORM_A = {
    "platform_id": "platform-a",
    "stack": "spring-postgres",
    "issuer_id": "issuerA",
    "subject_types": ["pv_module", "junction_box"],
    "port": 8081,
}

_PLATFORM_B = {
    "platform_id": "platform-b",
    "stack": "fastapi-mongo",
    "issuer_id": "issuerB",
    "subject_types": ["battery"],
    "port": 8082,
}

_VALID_PLATFORMS = [_PLATFORM_A, _PLATFORM_B]


def _make(platforms: list | None = None, resolver: dict | None = None) -> dict:
    data: dict = {"platforms": platforms if platforms is not None else _VALID_PLATFORMS}
    if resolver is not None:
        data["resolver"] = resolver
    return data


# ---------------------------------------------------------------------------
# Valid config
# ---------------------------------------------------------------------------


def test_valid_config_two_platforms():
    config = FederationConfig.model_validate(_make())
    assert len(config.platforms) == 2


def test_valid_config_platform_fields():
    config = FederationConfig.model_validate(_make())
    pa = config.platforms[0]
    assert pa.platform_id == "platform-a"
    assert pa.stack == StackType.SPRING_POSTGRES
    assert pa.issuer_id == "issuerA"
    assert "pv_module" in pa.subject_types
    assert pa.port == 8081


def test_resolver_defaults_to_port_8080():
    config = FederationConfig.model_validate(_make())
    assert config.resolver.port == 8080


def test_explicit_resolver_port():
    config = FederationConfig.model_validate(_make(resolver={"port": 9090}))
    assert config.resolver.port == 9090


def test_db_volume_defaults_from_platform_id():
    config = FederationConfig.model_validate(_make())
    assert config.platforms[0].db_volume == "platform-a-db"
    assert config.platforms[1].db_volume == "platform-b-db"


def test_db_volume_explicit_value_preserved():
    platforms = [{**_PLATFORM_A, "db_volume": "custom-vol"}, _PLATFORM_B]
    config = FederationConfig.model_validate(_make(platforms=platforms))
    assert config.platforms[0].db_volume == "custom-vol"


def test_both_stack_types_accepted():
    config = FederationConfig.model_validate(_make())
    stacks = {p.stack for p in config.platforms}
    assert StackType.SPRING_POSTGRES in stacks
    assert StackType.FASTAPI_MONGO in stacks


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------


def test_missing_platform_id_raises():
    bad = [{k: v for k, v in _PLATFORM_A.items() if k != "platform_id"}, _PLATFORM_B]
    with pytest.raises(ValidationError):
        FederationConfig.model_validate(_make(platforms=bad))


def test_missing_stack_raises():
    bad = [{k: v for k, v in _PLATFORM_A.items() if k != "stack"}, _PLATFORM_B]
    with pytest.raises(ValidationError):
        FederationConfig.model_validate(_make(platforms=bad))


def test_missing_port_raises():
    bad = [{k: v for k, v in _PLATFORM_A.items() if k != "port"}, _PLATFORM_B]
    with pytest.raises(ValidationError):
        FederationConfig.model_validate(_make(platforms=bad))


def test_missing_issuer_id_raises():
    bad = [{k: v for k, v in _PLATFORM_A.items() if k != "issuer_id"}, _PLATFORM_B]
    with pytest.raises(ValidationError):
        FederationConfig.model_validate(_make(platforms=bad))


def test_empty_platforms_list_raises():
    with pytest.raises(ValidationError):
        FederationConfig.model_validate(_make(platforms=[]))


def test_empty_subject_types_raises():
    bad = [{**_PLATFORM_A, "subject_types": []}, _PLATFORM_B]
    with pytest.raises(ValidationError):
        FederationConfig.model_validate(_make(platforms=bad))


# ---------------------------------------------------------------------------
# Invalid stack value
# ---------------------------------------------------------------------------


def test_invalid_stack_value_raises():
    bad = [{**_PLATFORM_A, "stack": "django-sqlite"}, _PLATFORM_B]
    with pytest.raises(ValidationError):
        FederationConfig.model_validate(_make(platforms=bad))


def test_stack_value_case_sensitive():
    bad = [{**_PLATFORM_A, "stack": "Spring-Postgres"}, _PLATFORM_B]
    with pytest.raises(ValidationError):
        FederationConfig.model_validate(_make(platforms=bad))


# ---------------------------------------------------------------------------
# Duplicate platform IDs
# ---------------------------------------------------------------------------


def test_duplicate_platform_ids_raises():
    dup = [_PLATFORM_A, {**_PLATFORM_B, "platform_id": "platform-a"}]
    with pytest.raises(ValueError, match="Duplicate platform ID"):
        FederationConfig.model_validate(_make(platforms=dup))


def test_duplicate_platform_ids_error_message_contains_id():
    dup = [_PLATFORM_A, {**_PLATFORM_B, "platform_id": "platform-a"}]
    with pytest.raises(ValueError, match="platform-a"):
        FederationConfig.model_validate(_make(platforms=dup))


# ---------------------------------------------------------------------------
# Port collisions
# ---------------------------------------------------------------------------


def test_port_collision_between_two_platforms():
    clash = [_PLATFORM_A, {**_PLATFORM_B, "port": 8081}]
    with pytest.raises(ValueError, match="Port 8081"):
        FederationConfig.model_validate(_make(platforms=clash))


def test_port_collision_error_names_both_services():
    clash = [_PLATFORM_A, {**_PLATFORM_B, "port": 8081}]
    with pytest.raises(ValueError) as exc_info:
        FederationConfig.model_validate(_make(platforms=clash))
    msg = str(exc_info.value)
    assert "platform-a" in msg or "platform-b" in msg


def test_port_collision_platform_vs_resolver():
    clash = [{**_PLATFORM_A, "port": 8080}, _PLATFORM_B]
    with pytest.raises(ValueError, match="Port 8080"):
        FederationConfig.model_validate(_make(platforms=clash, resolver={"port": 8080}))


def test_port_collision_resolver_named_in_error():
    clash = [{**_PLATFORM_A, "port": 8080}, _PLATFORM_B]
    with pytest.raises(ValueError) as exc_info:
        FederationConfig.model_validate(_make(platforms=clash, resolver={"port": 8080}))
    assert "resolver" in str(exc_info.value)


# ---------------------------------------------------------------------------
# load_config with real files
# ---------------------------------------------------------------------------


def test_load_config_valid_file(tmp_path: Path):
    config_file = tmp_path / "federation.yml"
    config_file.write_text(
        yaml.dump({"resolver": {"port": 8080}, "platforms": _VALID_PLATFORMS}),
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert len(config.platforms) == 2
    assert config.resolver.port == 8080


def test_load_config_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does-not-exist.yml")


def test_load_default_federation_yml():
    default_yml = Path(__file__).parent.parent / "default-federation.yml"
    config = load_config(default_yml)

    assert config.resolver.port == 8080

    platform_ids = {p.platform_id for p in config.platforms}
    assert "platform-a" in platform_ids
    assert "platform-b" in platform_ids

    stacks = {p.stack for p in config.platforms}
    assert StackType.SPRING_POSTGRES in stacks
    assert StackType.FASTAPI_MONGO in stacks

    for p in config.platforms:
        assert len(p.subject_types) >= 1
        assert p.db_volume is not None
