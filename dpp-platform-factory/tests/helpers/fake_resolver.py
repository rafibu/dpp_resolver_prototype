from typing import List, Dict, Optional
from dpp_platform_factory.core.state import PlatformRecord

class FakeResolverClient:
    def __init__(self, resolver_url: str):
        self.resolver_url = resolver_url
        self.platforms: Dict[str, dict] = {}
        self.schemas: List[dict] = []
        self.fail_registration: bool = False

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

    async def publish_schema(self, subject_type: str, schema: dict):
        self.schemas.append({"subject_type": subject_type, "schema": schema})
