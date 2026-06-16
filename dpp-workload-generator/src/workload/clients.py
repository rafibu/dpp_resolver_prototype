import asyncio
import httpx
import structlog
import time
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Any, List, Dict
from urllib.parse import quote, urlparse

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

    async def ensure_subject_type(self, subject_type: str) -> None:
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

    async def _register_subject_type(self, subject_type: str) -> None:
        await self.ensure_subject_type(subject_type)

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

    async def get_detail(self, dpp_id: str) -> dict:
        resp = await self._request("GET", f"/dpps/{dpp_id}")
        return resp.json()

    async def get_schema(self, subject_type: str, major: int, minor: int) -> dict:
        resp = await self._request("GET", f"/schemas/{subject_type}/{major}/{minor}")
        return resp.json()

    async def cache_schema(self, subject_type: str) -> None:
        await self._request("POST", f"/schemas/{subject_type}/cacheSchema", json={})

    async def supports_revision_import(self) -> bool:
        """Return whether this platform exposes the S1 revision-import endpoint.

        The probe uses an empty import list, which is a no-op on current platforms.
        It lets S1 avoid reusing stale successor containers that were built before
        the admin import endpoint existed.
        """
        try:
            await self._request("POST", "/admin/import-revisions", json=[])
            return True
        except DppNotFoundError:
            return False
        except WorkloadError as exc:
            logger.warning(
                "platform_import_revisions_probe_failed",
                platform_id=self.platform_info.platform_id,
                error=str(exc),
            )
            return False

    async def import_revisions(self, revisions: list[DppResponse]) -> None:
        """Copy existing revisions into a successor platform for issuer migration.

        Current platform builds expose an admin import endpoint because migration is
        not a new issue/revise transition. Live e2e runs can still encounter an
        older spawned platform image without that endpoint. In that case S1 falls
        back to the normal issue/revise API and then verifies that the recreated
        revisions have the same version, payload, and hash as the source revisions.
        """
        try:
            await self._request(
                "POST",
                "/admin/import-revisions",
                json=[revision.model_dump(mode="json") for revision in revisions],
            )
            return
        except DppNotFoundError:
            logger.warning(
                "platform_import_revisions_endpoint_missing",
                platform_id=self.platform_info.platform_id,
                fallback="issue_revise",
            )

        self._assert_public_replay_can_preserve_ids(revisions)
        await self._replay_imported_revisions(revisions)

    def _assert_public_replay_can_preserve_ids(self, revisions: list[DppResponse]) -> None:
        """Ensure issue/revise fallback can satisfy the platform issuer-prefix rule."""
        expected_prefix = f"{self.platform_info.issuer_id}-"
        mismatched = next(
            (revision.dpp_id for revision in revisions if not revision.dpp_id.startswith(expected_prefix)),
            None,
        )
        if mismatched is not None:
            raise WorkloadError(
                "Platform is missing /admin/import-revisions and public replay cannot preserve "
                f"source DPP ID {mismatched!r}: target platform {self.platform_info.platform_id} "
                f"uses issuer prefix {expected_prefix!r}. Rebuild the platform image with the "
                "admin import endpoint or choose an import-capable successor."
            )

    async def _replay_imported_revisions(self, revisions: list[DppResponse]) -> None:
        """Recreate imported revisions through issue/revise when admin import is absent."""
        for revision in sorted(revisions, key=lambda item: (item.dpp_id, item.version)):
            if revision.version < 1:
                raise WorkloadError(f"Cannot import non-positive revision version {revision.version}")

            if revision.version == 1:
                imported = await self._issue_imported_revision(revision)
            else:
                imported = await self._revise_imported_revision(revision)

            self._assert_imported_revision_matches(revision, imported)

    async def _issue_imported_revision(self, revision: DppResponse) -> DppResponse:
        """Issue a source revision-1 payload with its original DPP ID."""
        spec = IssueDppSpec(
            dpp_id=revision.dpp_id,
            schema_version=revision.schema_version,
            dpp_payload=revision.dpp_payload,
        )
        try:
            return await self.issue_dpp(spec)
        except ConflictError:
            return await self.get_revision(revision.dpp_id, revision.version)

    async def _revise_imported_revision(self, revision: DppResponse) -> DppResponse:
        """Append an imported successor revision with its original version number."""
        spec = ReviseDppSpec(
            version=revision.version,
            schema_version=revision.schema_version,
            dpp_payload=revision.dpp_payload,
        )
        try:
            return await self.revise_dpp(revision.dpp_id, spec)
        except ConflictError:
            return await self.get_revision(revision.dpp_id, revision.version)

    def _assert_imported_revision_matches(self, expected: DppResponse, actual: DppResponse) -> None:
        """Fail migration if fallback replay changes revision identity or content."""
        if (
            actual.dpp_id != expected.dpp_id
            or actual.version != expected.version
            or actual.schema_version != expected.schema_version
            or actual.dpp_payload != expected.dpp_payload
            or actual.payload_hash != expected.payload_hash
        ):
            raise WorkloadError(
                "Fallback import changed revision content: "
                f"expected {expected.dpp_id} v{expected.version} hash {expected.payload_hash}, "
                f"got {actual.dpp_id} v{actual.version} hash {actual.payload_hash}"
            )

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

        This method extends the issuer's existing mapping through the Resolver's
        dedicated subject-type support endpoint. It deliberately avoids register
        and migrate: the issuer already exists, and its platform/resolution URL must
        stay owned by the Factory so platform containers can follow redirects during
        the I7 hard-resolvability check.
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

        issuer_id = quote(platform.issuer_id, safe="")
        encoded_subject_type = quote(subject_type, safe="")
        await self._request("POST", f"/admin/platforms/{issuer_id}/subject-types/{encoded_subject_type}")

    async def ensure_platform_anchor(
        self,
        platform: PlatformInfo,
        anchor_issuer_id: str,
        subject_types: list[str],
    ) -> None:
        """Register a stable alias row so a migrated issuer can be restored later.

        The Resolver's migrate operation validates that the target platform name and
        resolution URL already exist in the registry. When S1 moves issuerB away from
        Platform B, that original row no longer names Platform B. This anchor keeps a
        harmless alias for the original physical platform so the final restore can use
        the normal migrate endpoint instead of inventing a special rollback path.
        """
        mappings = await self.list_platforms()
        resolution_base = platform.internal_url or platform.external_url
        resolution_url = f"{resolution_base.rstrip('/')}/dpps/{{dppId}}"
        entry = next(
            (m for m in mappings if (m.get("issuer_id") or m.get("issuerId")) == anchor_issuer_id),
            None,
        )

        if entry is None:
            await self._request("POST", "/admin/platforms/register", json={
                "platform": platform.platform_id,
                "resolution_url": resolution_url,
                "issuer_id": anchor_issuer_id,
                "subject_types": list(dict.fromkeys(subject_types)),
            })
            return

        existing_platform = entry.get("platform")
        existing_url = entry.get("resolution_url") or entry.get("resolutionUrl")
        if existing_platform != platform.platform_id or existing_url != resolution_url:
            raise WorkloadError(
                f"Resolver anchor {anchor_issuer_id} points to {existing_platform} ({existing_url}), "
                f"expected {platform.platform_id} ({resolution_url})"
            )

        existing_subject_types = set(entry.get("subject_types") or entry.get("subjectTypes") or [])
        for subject_type in subject_types:
            if subject_type not in existing_subject_types:
                issuer_id = quote(anchor_issuer_id, safe="")
                encoded_subject_type = quote(subject_type, safe="")
                await self._request(
                    "POST",
                    f"/admin/platforms/{issuer_id}/subject-types/{encoded_subject_type}",
                )

    async def migrate_platform(self, issuer_id: str, target_platform: PlatformInfo) -> dict:
        resolution_base = target_platform.internal_url or target_platform.external_url
        response = await self._request(
            "POST",
            f"/admin/platforms/{quote(issuer_id, safe='')}/migrate",
            json={
                "platform": target_platform.platform_id,
                "new_resolution_url": f"{resolution_base.rstrip('/')}/dpps/{{dppId}}",
            },
        )
        return response.json()

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

    async def resolve_revision(
        self,
        subject_type: str,
        dpp_id: str,
        version: int | None = None,
        redirect_base_url: str | None = None,
    ) -> httpx.Response:
        """Resolve a DPP and return the fully fetched platform response."""
        if redirect_base_url is not None:
            target_url = await self.resolve(subject_type, dpp_id, version)
            parsed_target = urlparse(target_url)
            fetch_url = f"{redirect_base_url.rstrip('/')}{parsed_target.path}"
            if parsed_target.query:
                fetch_url = f"{fetch_url}?{parsed_target.query}"
            response = await self._client.get(fetch_url, follow_redirects=True)
            response.raise_for_status()
            return response

        path = f"/{subject_type}/{dpp_id}" if version is None else f"/{subject_type}/{dpp_id}/{version}"
        return await self._request("GET", path, follow_redirects=True)

    async def resolve_revision_closure(
        self,
        subject_type: str,
        dpp_id: str,
        *,
        version: int,
        max_depth: int,
        redirect_base_url: str,
    ) -> httpx.Response:
        """Resolve a DPP and fetch its bounded platform closure response."""
        if max_depth < 1:
            raise ValueError("max_depth must be >= 1")

        target_url = await self.resolve(subject_type, dpp_id, version)
        parsed_target = urlparse(target_url)
        fetch_url = f"{redirect_base_url.rstrip('/')}{parsed_target.path.rstrip('/')}/closure"
        response = await self._client.get(
            fetch_url,
            params={"max_depth": max_depth},
            follow_redirects=True,
        )
        response.raise_for_status()
        return response
