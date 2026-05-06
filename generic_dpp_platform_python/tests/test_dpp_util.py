import pytest

from generic_dpp_platform.dpps.exceptions import SchemaValidationException
from generic_dpp_platform.dpps.utils import (
    hash_document,
    hash_to_hex,
    hex_to_hash,
    validate_dpp_document,
)

_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "serial_number": {"type": "string", "pattern": "^SN-\\d+$"},
        "recycled_content": {"type": "number", "minimum": 0, "maximum": 100},
        "nested": {
            "type": "object",
            "properties": {"inner": {"type": "string"}},
            "required": ["inner"],
        },
    },
    "required": ["serial_number"],
    "additionalProperties": False,
}


def test_validate_dpp_document_success():
    payload = {"serial_number": "SN-001", "recycled_content": 42.0}
    result = validate_dpp_document(payload, _SCHEMA)
    assert result == payload


def test_validate_dpp_document_failure():
    with pytest.raises(SchemaValidationException):
        validate_dpp_document({"recycled_content": 10}, _SCHEMA)


def test_validate_dpp_document_constraints_failure():
    with pytest.raises(SchemaValidationException):
        validate_dpp_document({"serial_number": "INVALID"}, _SCHEMA)

    with pytest.raises(SchemaValidationException):
        validate_dpp_document({"serial_number": "SN-1", "recycled_content": 200}, _SCHEMA)


def test_validate_dpp_document_additional_properties_failure():
    with pytest.raises(SchemaValidationException):
        validate_dpp_document({"serial_number": "SN-1", "extra_field": "bad"}, _SCHEMA)


def test_validate_dpp_document_nested_required_failure():
    with pytest.raises(SchemaValidationException):
        validate_dpp_document({"serial_number": "SN-1", "nested": {}}, _SCHEMA)


def test_hash_document_complex_deterministic():
    doc_a = {"b": 2, "a": 1, "c": {"z": 26, "y": 25}}
    doc_b = {"a": 1, "c": {"y": 25, "z": 26}, "b": 2}
    assert hash_document(doc_a) == hash_document(doc_b)


def test_hash_document_different_content():
    assert hash_document({"a": 1}) != hash_document({"a": 2})


def test_hex_conversion():
    original = hash_document({"serial_number": "SN-001", "manufacturer": "SolarCo"})
    hex_str = hash_to_hex(original)
    assert isinstance(hex_str, str)
    assert len(hex_str) == 64
    assert hex_str == hex_str.lower()
    recovered = hex_to_hash(hex_str)
    assert recovered == original


def test_hex_conversion_null():
    assert hash_to_hex(None) is None
    assert hex_to_hash(None) is None


def test_hex_to_hash_invalid():
    with pytest.raises((ValueError, Exception)):
        hex_to_hash("GGGG")

    with pytest.raises((ValueError, Exception)):
        hex_to_hash("abc")  # odd length
