"""
Bulk-loads seed schemas into the Resolver's authoritative schema set (Definition 6).

Schema artefacts (Definition 3) must exist on the Resolver before DPP platforms can
issue revisions that reference them (Invariant I3). The seed service reads the JSON Schema
2020-12 files from the seed-schemas/ directory and publishes them via the publishSchema
operation, registering each subject type first as a pre-condition.

This is a test-harness concern. In a real federation, schema publication would be
performed by domain governance authorities, not by a test controller.
"""
import json
from pathlib import Path
from typing import List, Optional

import structlog

from .state import FactoryState
from ..api.api_models import SeedSchemasSummary
from ..infrastructure.resolver_client import ResolverClient

logger = structlog.get_logger()


def _parse_schema_id(schema_content: dict) -> tuple[str, int, int]:
    """Parse subject type and version from a schema's $id field.

    Expects $id in the form: https://schemas.dpp.eu/{subject_type}/{major}.{minor}
    Raises ValueError if the $id is absent or does not match that pattern.
    """
    schema_id: str = schema_content.get("$id", "")
    if not schema_id:
        raise ValueError("Schema is missing the $id field")
    # Strip scheme+host: "https://schemas.dpp.eu/battery/1.0" -> "battery/1.0"
    marker = "dpp.eu/"
    idx = schema_id.find(marker)
    if idx == -1:
        raise ValueError(f"$id does not contain '{marker}': {schema_id!r}")
    path = schema_id[idx + len(marker):]
    parts = path.split("/")
    if len(parts) != 2:
        raise ValueError(f"Expected $id path of form '{{subject_type}}/{{major}}.{{minor}}', got: {path!r}")
    subject_type = parts[0]
    version_parts = parts[1].split(".")
    if len(version_parts) != 2:
        raise ValueError(f"Expected version of form '{{major}}.{{minor}}', got: {parts[1]!r}")
    try:
        major, minor = int(version_parts[0]), int(version_parts[1])
    except ValueError:
        raise ValueError(f"Version components must be integers, got: {parts[1]!r}")
    return subject_type, major, minor


class SchemaSeedService:
    def __init__(self, state: FactoryState, resolver_client_factory = ResolverClient):
        self.state = state
        self.resolver_client_factory = resolver_client_factory

    async def seed_schemas(self, requested_schemas: Optional[List[str]] = None) -> SeedSchemasSummary:
        schema_dir = Path("seed-schemas")
        if not schema_dir.exists():
            schema_dir = Path("dpp-platform-factory/seed-schemas")

        if not schema_dir.exists():
             raise RuntimeError("Schema directory not found")

        files = list(schema_dir.glob("*.json"))
        if requested_schemas:
            files = [f for f in files if f.name in requested_schemas]
            if len(files) < len(requested_schemas):
                found_names = {f.name for f in files}
                missing = [name for name in requested_schemas if name not in found_names]
                raise ValueError(f"Schemas not found: {missing}")

        async with self.state.lock:
            if not self.state.resolver:
                raise RuntimeError("Resolver not ready")
            resolver_url = self.state.resolver.internal_url

        resolver_client = self.resolver_client_factory(resolver_url)

        loaded = []
        failed = []

        for f in files:
            try:
                schema_content = json.loads(f.read_text())
                subject_type, major, minor = _parse_schema_id(schema_content)
                await resolver_client.ensure_subject_type(subject_type)
                await resolver_client.publish_schema(subject_type, major, minor, schema_content)
                loaded.append(f.name)
            except Exception as exc:
                failed.append(f"{f.name} ({str(exc)})")

        return SeedSchemasSummary(loaded=loaded, failed=failed)
