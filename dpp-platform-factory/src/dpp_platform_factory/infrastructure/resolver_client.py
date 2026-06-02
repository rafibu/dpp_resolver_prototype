"""
HTTP client for the Resolver's administrative endpoints.

The Resolver is the shared infrastructure component that holds the authoritative
schema set and the issuer-to-platform registry (Definition 6, Definition 10).
This client is used by the Factory to wire the federated state (Definition 7)
at startup and when new platforms are spawned.
"""
import httpx
import structlog

from ..core.state import PlatformRecord

logger = structlog.get_logger()


def _resolution_url(platform: PlatformRecord) -> str:
    return f"{platform.internal_url.rstrip('/')}/dpps/{{dppId}}"


class ResolverClient:
    def __init__(self, resolver_url: str) -> None:
        self._base_url = resolver_url.rstrip("/")

    async def ensure_subject_type(self, subject_type: str) -> None:
        """Register a subject type on the Resolver if it does not already exist.

        Subject types (Definition 3) must be registered before schemas can be published
        for them and before platforms can declare them as supported. This is a Factory
        bootstrap pre-condition, not a federated operation.
        """
        url = f"{self._base_url}/admin/subject-types"
        body = {
            "name": subject_type,
            "description": subject_type.replace("_", " ").title(),
        }

        logger.info("resolver_ensuring_subject_type", subject_type=subject_type, url=url)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=body)

        if response.status_code in (200, 201, 409):
            return

        if response.status_code == 400:
            # Current Resolver may return 400 for duplicates or validation errors.
            # Treat duplicate-like errors as harmless only if Resolver later exposes details.
            logger.warning(
                "resolver_subject_type_post_returned_400",
                subject_type=subject_type,
                body=response.text,
            )
            return

        raise RuntimeError(
            f"Resolver rejected subject type '{subject_type}': "
            f"HTTP {response.status_code} - {response.text}"
        )

    async def register_platform(self, platform: PlatformRecord) -> None:
        """Call POST /admin/platforms/register to execute registerIssuer.

        Adds an entry to the resolver registry (Definition 10) mapping the platform's
        issuer to its resolution URL and declared subject types. Existing issuers are
        rejected by the Resolver; callers must use migrate_platform for migrations.
        """
        url = f"{self._base_url}/admin/platforms/register"
        body = {
            "platform": platform.platform_id,
            # Internal Docker URL template: other platform containers follow the resolver
            # redirect over the Docker network during the I7 hard-reference check, and the
            # Resolver expands {dppId} (and appends the revision) when building the redirect.
            "resolution_url": _resolution_url(platform),
            "issuer_id": platform.issuer_id,
            "subject_types": platform.subject_types,
        }
        logger.info(
            "resolver_registering_platform",
            platform_id=platform.platform_id,
            url=url,
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=body)

        if response.status_code == 201:
            logger.info("resolver_registration_ok", platform_id=platform.platform_id)
            return

        raise RuntimeError(
            f"Resolver rejected registration of '{platform.platform_id}': "
            f"HTTP {response.status_code} - {response.text}"
        )

    async def migrate_platform(self, issuer_id: str, target_platform: PlatformRecord) -> None:
        """Call POST /admin/platforms/{issuerId}/migrate to execute migrate.

        Moves an already registered issuer to the target platform's resolution URL.
        The Resolver preserves the issuer's existing subject type set during migration.
        """
        url = f"{self._base_url}/admin/platforms/{issuer_id}/migrate"
        body = {
            "platform": target_platform.platform_id,
            "new_resolution_url": _resolution_url(target_platform),
        }
        logger.info(
            "resolver_migrating_platform",
            issuer_id=issuer_id,
            target_platform_id=target_platform.platform_id,
            url=url,
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=body)

        if response.status_code == 200:
            logger.info(
                "resolver_migration_ok",
                issuer_id=issuer_id,
                target_platform_id=target_platform.platform_id,
            )
            return

        raise RuntimeError(
            f"Resolver rejected migration of issuer '{issuer_id}' to "
            f"'{target_platform.platform_id}': HTTP {response.status_code} - {response.text}"
        )

    async def ensure_platform_mapping(self, platform: PlatformRecord) -> None:
        """Ensure bootstrap has an issuer mapping without treating startup as migrate.

        Bootstrap may run against a resolver database that already contains the default
        mappings. In that case the correct behavior is idempotent no-op, not a second
        register call. If the existing issuer points somewhere else, fail loudly so
        startup does not accidentally undo an intentional migration.
        """
        existing = await self.get_mapping_for_issuer(platform.issuer_id)
        if existing is None:
            await self.register_platform(platform)
            return

        existing_platform = existing.get("platform")
        existing_url = existing.get("resolution_url") or existing.get("resolutionUrl")
        existing_subject_types = set(existing.get("subject_types") or existing.get("subjectTypes") or [])
        expected_subject_types = set(platform.subject_types)
        expected_url = _resolution_url(platform)

        if (
            existing_platform == platform.platform_id
            and existing_url == expected_url
            and existing_subject_types == expected_subject_types
        ):
            logger.info(
                "resolver_mapping_already_registered",
                platform_id=platform.platform_id,
                issuer_id=platform.issuer_id,
            )
            return

        raise RuntimeError(
            f"Resolver already has issuer '{platform.issuer_id}' mapped to "
            f"'{existing_platform}' ({existing_url}); refusing to overwrite it during bootstrap"
        )

    async def get_mapping_for_issuer(self, issuer_id: str) -> dict | None:
        mappings = await self.list_platform_mappings()
        return next((
            mapping for mapping in mappings
            if (mapping.get("issuer_id") or mapping.get("issuerId")) == issuer_id
        ), None)

    async def list_platform_mappings(self) -> list[dict]:
        url = f"{self._base_url}/admin/platforms"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
        response.raise_for_status()
        return response.json()

    async def get_platform(self, platform_id: str) -> dict | None:
        mappings = await self.list_platform_mappings()
        return next((m for m in mappings if m.get("platform") == platform_id), None)

    async def publish_schema(
        self,
        subject_type: str,
        major_version: int,
        minor_version: int,
        schema_document: dict,
    ) -> None:
        """Call POST /schemas to execute the publishSchema operation.

        Adds a schema artefact (Definition 3) to the Resolver's authoritative schema set
        (Definition 6). The Resolver enforces Invariant I6 (schema-graph acyclicity) and
        returns 422 if publication would introduce a cycle.
        """
        url = f"{self._base_url}/schemas"
        body = {
            "subject_type": subject_type,
            "major_version": major_version,
            "minor_version": minor_version,
            "schema_document": schema_document,
        }
        logger.info(
            "resolver_publishing_schema",
            subject_type=subject_type,
            major=major_version,
            minor=minor_version,
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=body)
        response.raise_for_status()
