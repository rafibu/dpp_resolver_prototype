import asyncio
import httpx
import structlog
import time
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Any, List, Dict

from .federation import PlatformInfo

logger = structlog.get_logger(__name__)

class DppSchemaVersion(BaseModel):
    subject_type: str
    major_version: int
    minor_version: int

class DppResponse(BaseModel):
    dpp_id: str
    version: int
    schema_version: DppSchemaVersion
    dpp_payload: dict
    payload_hash: str
    created_at: datetime

class IssueDppSpec(BaseModel):
    dpp_id: Optional[str] = None
    schema_version: DppSchemaVersion
    dpp_payload: dict

class ReviseDppSpec(BaseModel):
    version: Optional[int] = None
    schema_version: DppSchemaVersion
    dpp_payload: dict

# Exceptions
class WorkloadError(Exception): pass
class DppNotFoundError(WorkloadError): pass
class SchemaValidationError(WorkloadError): pass
class CycleDetectedError(WorkloadError): pass
class ConflictError(WorkloadError): pass

class BaseClient:
    def __init__(self, base_url: str, follow_redirects: bool = False):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=follow_redirects)

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        start_time = time.perf_counter()
        for attempt in range(3):
            try:
                response = await self._client.request(method, f"{self.base_url}{path}", **kwargs)
                latency = (time.perf_counter() - start_time) * 1000
                
                # In Task 9 we will integrate this with MeasurementRecorder
                # For now, we log it.
                logger.debug("api_request", method=method, url=str(response.url), 
                             latency_ms=latency, status=response.status_code)
                
                if response.status_code == 404:
                    raise DppNotFoundError(f"Resource not found: {path}")
                if response.status_code == 400:
                    text = response.text
                    lower_text = text.lower()
                    if "SchemaValidationException" in text or "schema validation failed" in lower_text:
                        raise SchemaValidationError(text)
                    raise WorkloadError(f"Bad request: {text}")
                if response.status_code == 409:
                    text = response.text
                    if "DppCycleDetectedException" in text or "Cycle detected" in text:
                        raise CycleDetectedError(text)
                    raise ConflictError(text)
                
                if response.status_code == 422:
                    text = response.text
                    # Task R-8: schema cycles/self-ref
                    if "schema_cycle_detected" in text or "schema_self_reference" in text:
                         raise SchemaValidationError(text)
                    raise SchemaValidationError(text)

                response.raise_for_status()
                return response
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt == 2: raise
                logger.warning("api_request_retry", attempt=attempt+1, error=str(e))
                await asyncio.sleep(0.5 * (attempt + 1))
            except httpx.HTTPStatusError as e:
                # 5xx or other 4xx
                logger.error("api_request_failed", status=e.response.status_code, text=e.response.text)
                raise

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

class PlatformClient(BaseClient):
    def __init__(self, platform: PlatformInfo):
        super().__init__(platform.external_url)
        self.platform_info = platform

    async def _register_subject_type(self, subject_type: str) -> None:
        """Register a subject type on this platform.

        Platforms lose their subject type DB records after a Factory reset if the platform
        restarts with a fresh database before its startup initialization completes. Calling
        this before issuance restores the registration so DPP creation can proceed.
        """
        try:
            await self._request("POST", "/admin/subject-types", json={
                "name": subject_type,
                "description": subject_type.replace("_", " ").title()
            })
        except (WorkloadError, ConflictError):
            pass  # already registered

    async def issue_dpp(self, spec: IssueDppSpec) -> DppResponse:
        for attempt in range(3):
            try:
                resp = await self._request("POST", "/dpps/issue", json=spec.model_dump())
                return DppResponse.model_validate(resp.json())
            except WorkloadError as exc:
                if "Subject type not found" not in str(exc) or attempt >= 2:
                    raise
                # Platform lost its subject type records after reset. Re-register and retry.
                await self._register_subject_type(spec.schema_version.subject_type)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 500 or attempt >= 2:
                    raise
                # 500 is transient: MongoDB container was just rebuilt and is not yet
                # fully ready despite the platform's /health check having passed.
                logger.warning("platform_500_retry", attempt=attempt + 1,
                               url=str(exc.request.url))
                await asyncio.sleep(2.0)
        raise WorkloadError("issue_dpp failed after 3 attempts")

    async def revise_dpp(self, dpp_id: str, spec: ReviseDppSpec) -> DppResponse:
        resp = await self._request("POST", f"/dpps/{dpp_id}/revise", json=spec.model_dump())
        return DppResponse.model_validate(resp.json())

    async def get_revision(self, dpp_id: str, version: int | None = None) -> DppResponse:
        path = f"/dpps/{dpp_id}" if version is None else f"/dpps/{dpp_id}/{version}"
        resp = await self._request("GET", path)
        return DppResponse.model_validate(resp.json())

    async def get_schema(self, subject_type: str, major: int, minor: int) -> dict:
        resp = await self._request("GET", f"/schemas/{subject_type}/{major}/{minor}")
        return resp.json()

class ResolverClient(BaseClient):
    def __init__(self, base_url: str):
        super().__init__(base_url, follow_redirects=True)

    async def ensure_subject_type(self, subject_type: str) -> None:
        """Register a subject type on the Resolver if it does not already exist.

        Required before publishing a schema for a new subject type. The Resolver's
        SubjectTypeService is idempotent: duplicate registrations are silently ignored.
        """
        payload = {
            "name": subject_type,
            "description": subject_type.replace("_", " ").title()
        }
        try:
            await self._request("POST", "/admin/subject-types", json=payload)
        except (WorkloadError, ConflictError):
            pass  # already exists

    async def publish_schema(self, subject_type: str, major: int, minor: int, document: dict) -> None:
        # GET-first: the Resolver rejects duplicate publication with 400 and an empty body,
        # indistinguishable from other 400 errors. Checking existence first makes this
        # idempotent so scenarios can re-run without resetting the Resolver.
        try:
            await self._request("GET", f"/schemas/{subject_type}/{major}/{minor}")
            return  # already published
        except DppNotFoundError:
            pass  # 404 = not yet published, proceed

        payload = {
            "subject_type": subject_type,
            "major_version": major,
            "minor_version": minor,
            "schema_document": document
        }
        await self._request("POST", "/schemas", json=payload)

    async def get_schema(self, subject_type: str, major: int, minor: int) -> dict:
        resp = await self._request("GET", f"/schemas/{subject_type}/{major}/{minor}")
        # The Resolver API might return DppSchemaDTO
        data = resp.json()
        if isinstance(data, dict) and "schema_document" in data:
            return data["schema_document"]
        return data

    async def list_platforms(self) -> List[Dict[str, Any]]:
        resp = await self._request("GET", "/admin/platforms")
        return resp.json()

    async def ensure_platform_route(self, platform: PlatformInfo, subject_type: str) -> None:
        """Ensure the Resolver can route <subject_type>/<issuer>-* to the given platform.

        Invariant I7 requires hard references to be resolvable on the federated union. The
        Factory registers each platform's issuer-to-platform mapping once at spawn time with
        a fixed subject-type list. Subject types introduced later by workload scenarios
        (link_*, parent, child, inverter) are therefore absent from that mapping, so the
        Resolver returns 404 when a hard reference to such a DPP is resolved.

        This method merges the subject type into the issuer's existing mapping. The
        POST /admin/platforms upsert replaces the whole mapping, so the full merged
        subject-type list is re-sent along with the mapping's existing resolutionUrl, which is
        owned by the Factory (it must point at the platform's internal Docker URL so other
        platform containers can follow the resolver redirect during the I7 check). We never
        rewrite resolutionUrl here; doing so would risk replacing the internal URL with a
        host-only one and breaking container-to-container resolution.
        """
        mappings = await self.list_platforms()
        entry = next((m for m in mappings if m.get("issuer_id") == platform.issuer_id), None)

        if entry is None:
            logger.warning(
                "platform_mapping_missing",
                issuer_id=platform.issuer_id,
                subject_type=subject_type,
                hint="Resolver has no registry entry for this issuer; routing cannot be added.",
            )
            return

        subject_types = set(entry.get("subject_types", []))
        if subject_type in subject_types:
            return  # already routable, nothing to do
        subject_types.add(subject_type)

        body = {
            "platform": entry.get("platform", platform.platform_id),
            "issuer_id": platform.issuer_id,
            "resolution_url": entry["resolution_url"],
            "subject_types": sorted(subject_types),
        }
        await self._request("POST", "/admin/platforms", json=body)

    async def resolve(self, subject_type: str, dpp_id: str, version: int | None = None) -> str:
        """Return the resolver target without dereferencing Docker-internal redirects."""
        path = f"/{subject_type}/{dpp_id}" if version is None else f"/{subject_type}/{dpp_id}/{version}"
        start_time = time.perf_counter()
        response = await self._client.get(f"{self.base_url}{path}", follow_redirects=False)
        latency = (time.perf_counter() - start_time) * 1000
        logger.debug(
            "api_request",
            method="GET",
            url=str(response.url),
            latency_ms=latency,
            status=response.status_code,
        )
        if response.status_code == 404:
            raise DppNotFoundError(f"Resource not found: {path}")
        if response.is_redirect:
            return response.headers.get("location", str(response.url))
        response.raise_for_status()
        return str(response.url)
