import asyncio
from typing import List, Optional, Set

import httpx

from .platform import PlatformSpec, spawn_platform, teardown_platform, rebuild_db
from .state import FactoryState, PlatformStatus, PlatformRecord
from ..infrastructure.docker_client import DockerClient, DPP_NET
from ..infrastructure.resolver_client import ResolverClient


class PlatformService:
    def __init__(
        self, 
        state: FactoryState, 
        docker_client: DockerClient, 
        spawn_lock: asyncio.Lock,
        default_platform_ids: Set[str],
        resolver_client_factory = ResolverClient
    ):
        self.state = state
        self.docker_client = docker_client
        self.spawn_lock = spawn_lock
        self.default_platform_ids = default_platform_ids
        self.resolver_client_factory = resolver_client_factory

    async def list_platforms(self) -> List[PlatformRecord]:
        return await self.state.list_platforms()

    async def get_platform(self, platform_id: str) -> Optional[PlatformRecord]:
        return await self.state.get_platform(platform_id)

    async def spawn_platform(self, stack: str, issuer_id: str, subject_types: List[str]) -> PlatformRecord:
        """Spawn a new platform container and wire it into the federation.

        The operation is atomic: if Resolver registration fails (registerIssuer), 
        the containers are torn down and RuntimeError is raised.
        Only after a successful registration entry exists in the resolver registry
        (Definition 10) is the platform added to the factory's in-memory state.
        """
        if stack not in ("spring-postgres", "fastapi-mongo"):
            raise ValueError(f"Unsupported stack: {stack}")
        if not issuer_id:
            raise ValueError("issuer_id is required")
        if not subject_types:
            raise ValueError("subject_types cannot be empty")
        if any(not s.strip() for s in subject_types):
            raise ValueError("subject_types cannot contain empty strings")

        async with self.spawn_lock:
            # 1. Determine parameters
            async with self.state.lock:
                if not self.state.resolver:
                    raise RuntimeError("Resolver not ready")
                
                resolver_url_internal = self.state.resolver.internal_url
                resolver_url_external = self.state.resolver.external_url
                
                used_ports = self.state._used_ports_no_lock()
                next_port = 8084
                while next_port in used_ports:
                    next_port += 1
                
                count = len(self.state.platforms)
                platform_id = f"platform-{chr(ord('a') + count)}"
                while platform_id in self.state.platforms:
                    count += 1
                    platform_id = f"platform-{chr(ord('a') + count)}"

            # 2. Spawn platform
            spec = PlatformSpec(
                platform_id=platform_id,
                stack=stack,
                issuer_id=issuer_id,
                subject_types=subject_types,
                host_port=next_port
            )
            
            record = await spawn_platform(self.docker_client, DPP_NET, resolver_url_internal, spec)
            
            # 3. Register with Resolver
            try:
                resolver_client = self.resolver_client_factory(resolver_url_external)
                await resolver_client.register_platform(record)
            except Exception as reg_exc:
                # Atomic rollback
                try:
                    self.docker_client.stop_and_remove_by_id(record.container_id)
                    if record.db_container_id:
                        self.docker_client.stop_and_remove_by_id(record.db_container_id, remove_volumes=True)
                except Exception:
                    pass
                raise RuntimeError(f"Registration failed: {str(reg_exc)}")

            # 4. Add to state
            await self.state.add_platform(record)
            return record

    async def pause_platform(self, platform_id: str) -> PlatformRecord:
        record = await self.state.get_platform(platform_id)
        if not record:
            raise KeyError(f"Platform {platform_id} not found")
        
        if record.status == PlatformStatus.PAUSED:
            return record

        self.docker_client.stop_by_id(record.container_id)
        await self.state.update_status(platform_id, PlatformStatus.PAUSED)
        record.status = PlatformStatus.PAUSED
        return record

    async def resume_platform(self, platform_id: str) -> PlatformRecord:
        record = await self.state.get_platform(platform_id)
        if not record:
            raise KeyError(f"Platform {platform_id} not found")
        
        if record.status == PlatformStatus.RUNNING:
            return record

        self.docker_client.start_by_id(record.container_id)
        
        try:
            self.docker_client.wait_healthy(
                self.docker_client.get_container(record.container_id), 
                f"{record.internal_url}/health",
                timeout=30
            )
        except Exception as health_exc:
            await self.state.update_status(platform_id, PlatformStatus.ERROR)
            raise TimeoutError(f"Health check failed: {str(health_exc)}")

        await self.state.update_status(platform_id, PlatformStatus.RUNNING)
        record.status = PlatformStatus.RUNNING
        return record

    async def reset_platform(self, platform_id: str) -> PlatformRecord:
        record = await self.state.get_platform(platform_id)
        if not record:
            raise KeyError(f"Platform {platform_id} not found")
        
        if record.status == PlatformStatus.PAUSED:
            raise ValueError("Cannot reset a paused platform")

        try:
            # 1. Stop platform
            self.docker_client.stop_by_id(record.container_id)
            
            # 2. Rebuild DB
            new_db_id = await rebuild_db(self.docker_client, record, DPP_NET)
            record.db_container_id = new_db_id
            
            # 3. Start platform
            self.docker_client.start_by_id(record.container_id)
            
            # 4. Wait healthy
            try:
                self.docker_client.wait_healthy(
                    self.docker_client.get_container(record.container_id), 
                    f"{record.internal_url}/health",
                    timeout=30
                )
            except Exception as health_exc:
                await self.state.update_status(platform_id, PlatformStatus.ERROR)
                raise TimeoutError(f"Health check failed after reset: {str(health_exc)}")

            # 5. Re-register with Resolver
            resolver_url_external = None
            async with self.state.lock:
                 if not self.state.resolver:
                     raise RuntimeError("Resolver not ready")
                 resolver_url_external = self.state.resolver.external_url
                 
            resolver_client = self.resolver_client_factory(resolver_url_external)
            await resolver_client.register_platform(record)

            await self.state.update_status(platform_id, PlatformStatus.RUNNING)
            record.status = PlatformStatus.RUNNING
            
            async with self.state.lock:
                 if platform_id in self.state.platforms:
                     self.state.platforms[platform_id].db_container_id = new_db_id

            return record
        except Exception as exc:
            await self.state.update_status(platform_id, PlatformStatus.ERROR)
            raise exc

    async def delete_platform(self, platform_id: str):
        record = await self.state.get_platform(platform_id)
        if not record:
            raise KeyError(f"Platform {platform_id} not found")
        
        if platform_id in self.default_platform_ids:
            raise PermissionError("Default platforms cannot be deleted")

        await teardown_platform(self.docker_client, record)
        await self.state.remove_platform(platform_id)

    async def get_platform_cache(self, platform_id: str) -> List[dict]:
        """Fetch external cache from a platform."""
        record = await self.state.get_platform(platform_id)
        if not record:
            raise KeyError(f"Platform {platform_id} not found")
        
        url = f"{record.internal_url}/admin/cache"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
