import httpx
import structlog
from datetime import datetime
from enum import Enum
from pydantic import BaseModel
from typing import List, Optional

logger = structlog.get_logger(__name__)

class PlatformStatus(str, Enum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"

class PlatformInfo(BaseModel):
    platform_id: str
    stack: str
    issuer_id: str
    subject_types: List[str]
    external_url: str
    status: PlatformStatus
    created_at: datetime

class ResolverInfo(BaseModel):
    external_url: str
    status: PlatformStatus

class FederationOverview(BaseModel):
    resolver: Optional[ResolverInfo]
    platforms: List[PlatformInfo]

class FederationClient:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=10.0)
        self._overview: Optional[FederationOverview] = None

    async def discover(self, factory_url: str) -> FederationOverview:
        """Fetch federation overview from Factory and cache it."""
        if self._overview:
            return self._overview
        
        logger.info("factory_discover", factory_url=factory_url)
        try:
            response = await self._client.get(f"{factory_url.rstrip('/')}/federation")
            response.raise_for_status()
            self._overview = FederationOverview.model_validate(response.json())
            logger.info("factory_discovered", 
                        platform_count=len(self._overview.platforms),
                        resolver_url=self._overview.resolver.external_url if self._overview.resolver else None)
            return self._overview
        except Exception as e:
            logger.error("factory_discovery_failed", error=str(e), factory_url=factory_url)
            raise

    async def find_platform_for_subject_type(self, subject_type: str) -> PlatformInfo:
        """Find a platform that handles the given subject type."""
        if not self._overview:
            raise RuntimeError("Federation not discovered yet. Call discover() first.")
        
        for platform in self._overview.platforms:
            if subject_type in platform.subject_types:
                return platform
        
        raise ValueError(f"No platform found for subject type: {subject_type}")

    async def all_platforms(self) -> List[PlatformInfo]:
        """Return all platforms in the federation."""
        if not self._overview:
            raise RuntimeError("Federation not discovered yet. Call discover() first.")
        return self._overview.platforms

    async def resolver_url(self) -> str:
        """Return the Resolver URL."""
        if not self._overview:
            raise RuntimeError("Federation not discovered yet. Call discover() first.")
        if not self._overview.resolver:
            raise RuntimeError("No resolver info available in federation.")
        return self._overview.resolver.external_url

    async def reset_all_platforms(self, factory_url: str):
        """Reset all platforms by calling POST /admin/reset directly on each platform.

        Calls the platform's own reset endpoint, which deletes DPP revisions and the
        external cache without touching the DB container or subject type registrations.
        The Factory's POST /platforms/{id}/reset rebuilds the entire DB container, which
        breaks MongoDB replica-set configuration and causes transaction errors on writes.
        Direct platform reset avoids that entirely.
        """
        if not self._overview:
            await self.discover(factory_url)

        for platform in self._overview.platforms:
            logger.info("platform_reset", platform_id=platform.platform_id)
            try:
                response = await self._client.post(
                    f"{platform.external_url.rstrip('/')}/admin/reset",
                    timeout=15.0
                )
                response.raise_for_status()
                logger.info("platform_reset_ok", platform_id=platform.platform_id)
            except Exception as e:
                logger.warning("platform_reset_failed", platform_id=platform.platform_id,
                               error=str(e))

    async def pause_platform(self, factory_url: str, platform_id: str):
        """Pause a platform in the federation via Factory."""
        logger.info("factory_pause_platform", platform_id=platform_id)
        response = await self._client.post(f"{factory_url.rstrip('/')}/platforms/{platform_id}/pause")
        response.raise_for_status()

    async def resume_platform(self, factory_url: str, platform_id: str):
        """Resume a platform in the federation via Factory."""
        logger.info("factory_resume_platform", platform_id=platform_id)
        response = await self._client.post(f"{factory_url.rstrip('/')}/platforms/{platform_id}/resume")
        response.raise_for_status()

    async def seed_schemas(self, factory_url: str):
        """Seed schemas in the Resolver via Factory."""
        logger.info("factory_seed_schemas")
        response = await self._client.post(f"{factory_url.rstrip('/')}/resolver/seed-schemas")
        response.raise_for_status()

    async def get_platform_cache(self, factory_url: str, platform_id: str) -> List[dict]:
        """Fetch platform cache via Factory."""
        response = await self._client.get(f"{factory_url.rstrip('/')}/platforms/{platform_id}/cache")
        response.raise_for_status()
        return response.json()

    async def close(self):
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
