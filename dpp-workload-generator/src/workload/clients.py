import asyncio
import time
import httpx
import structlog
from typing import Optional, Any, List, Dict
from datetime import datetime
from pydantic import BaseModel
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
                    if "SchemaValidationException" in text or "Schema validation failed" in text:
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

    async def issue_dpp(self, spec: IssueDppSpec) -> DppResponse:
        resp = await self._request("POST", "/dpps/issue", json=spec.model_dump())
        return DppResponse.model_validate(resp.json())

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
        payload = {
            "subjectType": subject_type,
            "majorVersion": major,
            "minorVersion": minor,
            "schemaDocument": document
        }
        await self._request("POST", "/schemas", json=payload)

    async def get_schema(self, subject_type: str, major: int, minor: int) -> dict:
        resp = await self._request("GET", f"/schemas/{subject_type}/{major}/{minor}")
        # The Resolver API might return DppSchemaDTO
        data = resp.json()
        if isinstance(data, dict) and "schemaDocument" in data:
            return data["schemaDocument"]
        return data

    async def list_platforms(self) -> List[Dict[str, Any]]:
        resp = await self._request("GET", "/admin/platforms")
        return resp.json()

    async def resolve(self, subject_type: str, dpp_id: str, version: int | None = None) -> str:
        """Returns the resolved URL after following redirects."""
        path = f"/{subject_type}/{dpp_id}" if version is None else f"/{subject_type}/{dpp_id}/{version}"
        resp = await self._request("GET", path)
        return str(resp.url)
