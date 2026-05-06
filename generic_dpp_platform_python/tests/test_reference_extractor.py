import pytest

from generic_dpp_platform.dpps.models import DependencyType
from generic_dpp_platform.dpps.reference_extractor import extract_references


def test_extract_hard_reference():
    payload = {"battery": {"$ref": "battery/issuerB-bat-001", "version": 1}}
    refs = extract_references(payload)
    assert len(refs) == 1
    ref = refs[0]
    assert ref.subject_type == "battery"
    assert ref.dpp_id == "issuerB-bat-001"
    assert ref.version == 1
    assert ref.dependency_type == DependencyType.HARD


def test_extract_soft_reference():
    payload = {"battery": {"$ref": "battery/issuerB-bat-001"}}
    refs = extract_references(payload)
    assert len(refs) == 1
    ref = refs[0]
    assert ref.version is None
    assert ref.dependency_type == DependencyType.SOFT


def test_extract_tolerated_hard_reference_version_in_path():
    payload = {"battery": {"$ref": "battery/issuerB-bat-001/1"}}
    refs = extract_references(payload)
    assert len(refs) == 1
    ref = refs[0]
    assert ref.version == 1
    assert ref.dependency_type == DependencyType.HARD


def test_extract_nested_references():
    payload = {
        "components": {
            "battery": {"$ref": "battery/issuerB-bat-001", "version": 1},
            "details": {
                "inverter": {"$ref": "inverter/issuerC-inv-001", "version": 2},
            },
        },
        "metadata": {
            "supplier_dpp": {"$ref": "supplier/issuerD-sup-001"},
        },
    }
    refs = extract_references(payload)
    assert len(refs) == 3
    types = {r.dependency_type for r in refs}
    assert DependencyType.HARD in types
    assert DependencyType.SOFT in types


def test_invalid_reference_format():
    payload = {"ref": {"$ref": "invalid-format-no-slash"}}
    with pytest.raises(ValueError, match="Invalid DPP reference format"):
        extract_references(payload)


def test_conflicting_versions_raise_error():
    payload = {"ref": {"$ref": "battery/issuerB-bat-001/1", "version": 2}}
    with pytest.raises(ValueError, match="Conflicting version"):
        extract_references(payload)
