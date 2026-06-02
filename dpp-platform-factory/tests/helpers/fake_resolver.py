from typing import List, Dict, Optional

from dpp_platform_factory.core.state import PlatformRecord


class FakeResolverClient:
    def __init__(self, resolver_url: str):
        self.resolver_url = resolver_url
        self.platforms: Dict[str, dict] = {}
        self.schemas: List[dict] = []
        self.subject_types: List[str] = []
        self.fail_registration: bool = False
        self.register_calls: List[str] = []
        self.migration_calls: List[tuple[str, str]] = []

    async def ensure_subject_type(self, subject_type: str) -> None:
        if subject_type not in self.subject_types:
            self.subject_types.append(subject_type)

    async def register_platform(self, platform: PlatformRecord):
        if self.fail_registration:
            raise RuntimeError("Simulated Resolver failure")
        if any(mapping["issuer_id"] == platform.issuer_id for mapping in self.platforms.values()):
            raise RuntimeError("Issuer already registered, use migrate instead")

        self.register_calls.append(platform.platform_id)
        self.platforms[platform.platform_id] = {
            "platform": platform.platform_id,
            "resolution_url": f"{platform.internal_url.rstrip('/')}/dpps/{{dppId}}",
            "issuer_id": platform.issuer_id,
            "subject_types": platform.subject_types,
        }

    async def migrate_platform(self, issuer_id: str, target_platform: PlatformRecord):
        source = next((mapping for mapping in self.platforms.values() if mapping["issuer_id"] == issuer_id), None)
        if source is None:
            raise RuntimeError("Issuer not registered, use register if it should be added")
        if target_platform.platform_id not in self.platforms:
            raise RuntimeError("Platform not registered, use register if it should be added")

        self.migration_calls.append((issuer_id, target_platform.platform_id))
        source["platform"] = target_platform.platform_id
        source["resolution_url"] = f"{target_platform.internal_url.rstrip('/')}/dpps/{{dppId}}"

    async def ensure_platform_mapping(self, platform: PlatformRecord):
        existing = next((mapping for mapping in self.platforms.values() if mapping["issuer_id"] == platform.issuer_id), None)
        expected_url = f"{platform.internal_url.rstrip('/')}/dpps/{{dppId}}"
        if existing is None:
            await self.register_platform(platform)
            return
        if (
            existing["platform"] == platform.platform_id
            and existing["resolution_url"] == expected_url
            and set(existing["subject_types"]) == set(platform.subject_types)
        ):
            return
        raise RuntimeError("Issuer already registered with a different mapping")

    async def get_platform(self, platform_id: str) -> Optional[dict]:
        return self.platforms.get(platform_id)

    async def publish_schema(
        self,
        subject_type: str,
        major_version: int,
        minor_version: int,
        schema_document: dict,
    ) -> None:
        self.schemas.append({
            "subject_type": subject_type,
            "major_version": major_version,
            "minor_version": minor_version,
            "schema_document": schema_document,
        })
