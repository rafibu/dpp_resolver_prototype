from typing import List, Dict, Optional
from dpp_platform_factory.core.state import PlatformRecord

class FakeResolverClient:
    def __init__(self, resolver_url: str):
        self.resolver_url = resolver_url
        self.platforms: Dict[str, dict] = {}
        self.schemas: List[dict] = []
        self.subject_types: List[str] = []
        self.fail_registration: bool = False

    async def ensure_subject_type(self, subject_type: str) -> None:
        if subject_type not in self.subject_types:
            self.subject_types.append(subject_type)

    async def register_platform(self, platform: PlatformRecord):
        if self.fail_registration:
            raise RuntimeError("Simulated Resolver failure")

        self.platforms[platform.platform_id] = {
            "platformId": platform.platform_id,
            "baseUrl": platform.external_url,
            "issuerId": platform.issuer_id,
            "subjectTypes": platform.subject_types,
        }

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
