import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum


class PlatformStatus(str, Enum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"


@dataclass
class PlatformRecord:
    """Factory-internal runtime record for a managed DPP platform container.

    Not a formal model type. Tracks the Docker container IDs and port mapping
    alongside the platform's logical identity (issuer_id, subject_types) which
    mirrors what the Resolver registry (Definition 10) stores for routing.
    """
    platform_id: str
    stack: str
    issuer_id: str
    subject_types: list[str]
    container_id: str
    db_container_id: str
    external_url: str
    internal_url: str
    status: PlatformStatus
    created_at: datetime


@dataclass
class ResolverRecord:
    """Factory-internal runtime record for the managed Resolver container.

    Not a formal model type. Tracks the container IDs and both the external URL
    (used by the Frontend and Workload Generator) and the internal Docker-network
    URL (used by platform containers to reach the Resolver for I3/I7 checks).
    """
    container_id: str
    db_container_id: str
    external_url: str
    internal_url: str
    status: PlatformStatus
    started_at: datetime


class FactoryState:
    """Thread-safe (asyncio.Lock) registry of all managed containers."""

    def __init__(self) -> None:
        self._lock_obj: asyncio.Lock | None = None
        self.resolver: ResolverRecord | None = None
        self.platforms: dict[str, PlatformRecord] = {}

    @property
    def lock(self) -> asyncio.Lock:
        """Lazy-init the lock to ensure it binds to the correct event loop."""
        if self._lock_obj is None:
            self._lock_obj = asyncio.Lock()
        return self._lock_obj

    # ------------------------------------------------------------------
    # Resolver
    # ------------------------------------------------------------------

    async def set_resolver(self, record: ResolverRecord) -> None:
        async with self.lock:
            self.resolver = record

    async def get_resolver(self) -> ResolverRecord | None:
        async with self.lock:
            return self.resolver

    # ------------------------------------------------------------------
    # Platforms
    # ------------------------------------------------------------------

    async def add_platform(self, record: PlatformRecord) -> None:
        async with self.lock:
            self.platforms[record.platform_id] = record

    async def get_platform(self, platform_id: str) -> PlatformRecord | None:
        async with self.lock:
            return self.platforms.get(platform_id)

    async def remove_platform(self, platform_id: str) -> PlatformRecord | None:
        async with self.lock:
            return self.platforms.pop(platform_id, None)

    async def update_status(self, platform_id: str, status: PlatformStatus) -> None:
        async with self.lock:
            if platform_id in self.platforms:
                self.platforms[platform_id].status = status

    async def list_platforms(self) -> list[PlatformRecord]:
        async with self.lock:
            return list(self.platforms.values())

    async def used_ports(self) -> set[int]:
        """Return all host ports currently allocated to managed platforms."""
        async with self.lock:
            return self._used_ports_no_lock()

    def _used_ports_no_lock(self) -> set[int]:
        ports: set[int] = set()
        for p in self.platforms.values():
            if not p.external_url:
                continue
            try:
                port = int(p.external_url.rsplit(":", 1)[-1])
                ports.add(port)
            except (ValueError, IndexError):
                pass
        return ports

    # ------------------------------------------------------------------
    # Serialization (for debugging only - not for persistence)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        def _serialize(value):
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, list):
                return [_serialize(v) for v in value]
            return value

        result: dict = {}
        if self.resolver:
            result["resolver"] = {k: _serialize(v) for k, v in asdict(self.resolver).items()}
        else:
            result["resolver"] = None
        result["platforms"] = {
            pid: {k: _serialize(v) for k, v in asdict(p).items()}
            for pid, p in self.platforms.items()
        }
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
