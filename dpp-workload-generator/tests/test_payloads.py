import pytest
import jsonschema
from workload.payloads import generate_valid_payload, generate_invalid_payload, generate_dpp_id, ReferenceSpec
from workload.schemas import generate_schema

def test_generate_dpp_id():
    assert generate_dpp_id("issuerA", "pv_module", 1) == "issuerA-pv-001"
    assert generate_dpp_id("issuerB", "battery", 42) == "issuerB-ba-042"

def test_determinism():
    schema = generate_schema("pv")
    p1 = generate_valid_payload(schema, seed=42)
    p2 = generate_valid_payload(schema, seed=42)
    p3 = generate_valid_payload(schema, seed=43)
    
    assert p1 == p2
    assert p1 != p3

def test_valid_payload_validation():
    schema = generate_schema("pv", with_dependencies=True)
    dependencies = [ReferenceSpec(subject_type="battery", dpp_id="ba-001", version=1)]
    payload = generate_valid_payload(schema, dependencies=dependencies, seed=42)
    
    # Validate against schema
    jsonschema.validate(instance=payload, schema=schema)
    assert payload["manufacturer"].startswith("Manufacturer-")
    assert len(payload["dependencies"]) == 1
    assert payload["dependencies"][0]["$ref"] == "battery/ba-001"
    assert payload["dependencies"][0]["version"] == 1

def test_invalid_payloads():
    schema = generate_schema("pv")
    
    # Missing required field
    p_missing = generate_invalid_payload(schema, "missing_required_field", seed=42)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=p_missing, schema=schema)
        
    # Wrong type
    p_type = generate_invalid_payload(schema, "wrong_type", seed=42)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=p_type, schema=schema)
        
    # Out of range
    p_range = generate_invalid_payload(schema, "out_of_range", seed=42)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=p_range, schema=schema)
