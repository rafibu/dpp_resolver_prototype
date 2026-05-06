import pytest
from workload.schemas import generate_schema

def test_generate_schema_basic():
    schema = generate_schema("pv_module")
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "manufacturer" in schema["properties"]
    assert "dependencies" not in schema["properties"]
    assert "recycled_content" in schema["properties"]

def test_generate_schema_with_dependencies():
    schema = generate_schema("pv_module", with_dependencies=True, dependency_count=2)
    assert "dependencies" in schema["properties"]
    assert schema["properties"]["dependencies"]["type"] == "array"
    assert schema["properties"]["dependencies"]["minItems"] == 2
    
    items = schema["properties"]["dependencies"]["items"]
    assert "$ref" in items["properties"]
    assert "version" in items["properties"]

def test_generate_schema_required_fields():
    schema = generate_schema("test")
    assert set(schema["required"]) == {"manufacturer", "model", "serial_number"}
