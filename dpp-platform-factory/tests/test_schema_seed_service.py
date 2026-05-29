import pytest
from dpp_platform_factory.core.schema_seed_service import _parse_schema_id


def test_parse_battery_schema_id():
    schema = {"$id": "https://schemas.dpp.eu/battery/1.0"}
    subject_type, major, minor = _parse_schema_id(schema)
    assert subject_type == "battery"
    assert major == 1
    assert minor == 0


def test_parse_pv_module_schema_id():
    schema = {"$id": "https://schemas.dpp.eu/pv_module/1.0"}
    subject_type, major, minor = _parse_schema_id(schema)
    assert subject_type == "pv_module"
    assert major == 1
    assert minor == 0


def test_parse_schema_id_non_zero_minor():
    schema = {"$id": "https://schemas.dpp.eu/battery/2.3"}
    subject_type, major, minor = _parse_schema_id(schema)
    assert subject_type == "battery"
    assert major == 2
    assert minor == 3


def test_parse_schema_id_missing_raises():
    with pytest.raises(ValueError, match="missing the \\$id"):
        _parse_schema_id({})


def test_parse_schema_id_wrong_host_raises():
    schema = {"$id": "https://schemas.example.com/battery/1.0"}
    with pytest.raises(ValueError, match="dpp.eu/"):
        _parse_schema_id(schema)


def test_parse_schema_id_missing_version_raises():
    schema = {"$id": "https://schemas.dpp.eu/battery"}
    with pytest.raises(ValueError, match="subject_type"):
        _parse_schema_id(schema)


def test_parse_schema_id_bad_version_raises():
    schema = {"$id": "https://schemas.dpp.eu/battery/one.zero"}
    with pytest.raises(ValueError, match="integers"):
        _parse_schema_id(schema)
