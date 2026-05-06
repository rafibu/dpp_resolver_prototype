import json
from pathlib import Path
from typing import List, Optional

import structlog

from .state import FactoryState
from ..api.api_models import SeedSchemasSummary
from ..infrastructure.resolver_client import ResolverClient

logger = structlog.get_logger()

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
                subject_type = schema_content.get("title", f.stem)
                await resolver_client.publish_schema(subject_type, schema_content)
                loaded.append(f.name)
            except Exception as exc:
                failed.append(f"{f.name} ({str(exc)})")

        return SeedSchemasSummary(loaded=loaded, failed=failed)
