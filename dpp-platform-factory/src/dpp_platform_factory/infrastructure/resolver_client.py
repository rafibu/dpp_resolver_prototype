import structlog
import httpx

from ..core.state import PlatformRecord

logger = structlog.get_logger()


class ResolverClient:
    def __init__(self, resolver_url: str) -> None:
        self._base_url = resolver_url.rstrip("/")

    async def ensure_subject_type(self, subject_type: str) -> None:
        """Ensure a Resolver subject type exists before platform registration."""
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
        """Call POST /platforms on the Resolver. Re-registration (upsert) is always accepted."""
        url = f"{self._base_url}/admin/platforms"
        body = {
            "platform": platform.platform_id,
            "resolutionUrl": platform.external_url,
            "issuerId": platform.issuer_id,
            "subjectTypes": platform.subject_types,
        }
        logger.info(
            "resolver_registering_platform",
            platform_id=platform.platform_id,
            url=url,
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=body)

        if response.status_code in (200, 201):
            logger.info("resolver_registration_ok", platform_id=platform.platform_id)
            return

        raise RuntimeError(
            f"Resolver rejected registration of '{platform.platform_id}': "
            f"HTTP {response.status_code} — {response.text}"
        )

    async def get_platform(self, platform_id: str) -> dict | None:
        url = f"{self._base_url}/platforms/{platform_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def publish_schema(self, subject_type: str, schema: dict) -> None:
        url = f"{self._base_url}/schemas"
        logger.info("resolver_publishing_schema", subject_type=subject_type)
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=schema)
        response.raise_for_status()
