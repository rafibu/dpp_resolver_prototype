import structlog
from typing import List
from ..clients import ResolverClient

logger = structlog.get_logger(__name__)

def generate_schema(
    subject_type: str,
    with_dependencies: bool = False,
    dependency_count: int = 0,
    hard_reference_targets: list[str] | None = None,
) -> dict:
    """
    Generate a minimal but realistic JSON Schema 2020-12 document.

    Standard fields: manufacturer, model, recycled_content (number 0-100), serial_number.
    Optional dependencies field as an array of reference objects when with_dependencies=True.
    Each reference object shape: {"$ref": "<identity>", "version": <int>}

    hard_reference_targets: if provided, adds a property per target subject type annotated
    with "x-dpp-reference": "<target>". The Resolver's HardReferenceExtractor reads these
    annotations to build the schema dependency graph (Definition 13) and enforce I6 acyclicity.
    """
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://dpp.example.org/schemas/{subject_type}",
        "title": f"DPP Schema for {subject_type}",
        "type": "object",
        "properties": {
            "manufacturer": {"type": "string"},
            "model": {"type": "string"},
            "recycled_content": {
                "type": "number",
                "minimum": 0,
                "maximum": 100
            },
            "serial_number": {"type": "string"}
        },
        "required": ["manufacturer", "model", "serial_number"],
        "additionalProperties": False
    }

    if with_dependencies:
        ref_schema = {
            "type": "object",
            "properties": {
                "$ref": {"type": "string", "pattern": "^[^/]+/[^/]+(?:/\\d+)?$"},
                "version": {"type": "integer", "minimum": 1}
            },
            "required": ["$ref"],
            "additionalProperties": False
        }
        schema["properties"]["dependencies"] = {
            "type": "array",
            "items": ref_schema
        }
        if dependency_count > 0:
            schema["properties"]["dependencies"]["minItems"] = dependency_count

    if hard_reference_targets:
        for target in hard_reference_targets:
            field_name = f"{target}_ref"
            schema["properties"][field_name] = {
                "type": "object",
                "x-dpp-reference": target,
                "properties": {
                    "$ref": {"type": "string"},
                    "version": {"type": "integer", "minimum": 1}
                },
                "required": ["$ref"]
            }

    return schema

async def seed_resolver_schemas(resolver: ResolverClient, subject_types: List[str]) -> None:
    """Seed multiple schemas (version 1.0) in the Resolver."""
    for st in subject_types:
        # All scenario schemas are allowed to have dependencies
        schema = generate_schema(st, with_dependencies=True)
        logger.info("seeding_schema", subject_type=st, version="1.0")
        await resolver.publish_schema(st, 1, 0, schema)
