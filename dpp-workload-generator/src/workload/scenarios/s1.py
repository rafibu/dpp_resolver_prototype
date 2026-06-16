import asyncio
import copy
import httpx
import structlog
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .reporter import ScenarioReporter
from ..clients import DppResponse, DppSchemaVersion, IssueDppSpec, PlatformClient, ResolverClient, ReviseDppSpec
from ..federation import FederationClient, PlatformInfo, PlatformStatus

logger = structlog.get_logger(__name__)

INVERTER_TYPE = "s1_inverter"
INSTALLATION_TYPE = "s1_pv_installation"


class _S1SetupFailed(RuntimeError):
    """Raised after the setup step has already recorded its concrete failure."""


async def run_s1(factory_url: str, seed: int, output_dir: Optional[Path] = None) -> bool:
    """Scenario S1: Federated Reference Stability Under Target Evolution and Issuer Migration."""
    reporter = ScenarioReporter(
        "s1",
        "Federated Reference Stability Under Target Evolution and Issuer Migration",
        output_dir=output_dir,
    )

    async with FederationClient() as fed_client:
        resolver: ResolverClient | None = None
        pv_platform: PlatformInfo | None = None
        inverter_platform: PlatformInfo | None = None
        successor_platform: PlatformInfo | None = None
        inverter_v1: DppResponse | None = None
        inverter_v2: DppResponse | None = None
        installation_v1: DppResponse | None = None
        initial_hard_target = ""

        with reporter.step(
            "Setup federation, schemas, and issuer routes",
            "PV issuer routes to Platform A; inverter issuer routes to Platform B; successor Platform C is ready",
        ):
            fed = await fed_client.discover(factory_url)
            await fed_client.reset_all_platforms(factory_url)
            resolver = ResolverClient(await fed_client.resolver_url())

            pv_platform = await fed_client.find_platform_for_subject_type("pv_module")
            inverter_platform = await fed_client.find_platform_for_subject_type("inverter")

            await resolver.ensure_subject_type(INVERTER_TYPE)
            await resolver.ensure_subject_type(INSTALLATION_TYPE)
            await resolver.publish_schema(INVERTER_TYPE, 1, 0, _inverter_schema())
            await resolver.publish_schema(INSTALLATION_TYPE, 1, 0, _installation_schema())
            await resolver.ensure_platform_route(pv_platform, INSTALLATION_TYPE)
            await resolver.ensure_platform_route(inverter_platform, INVERTER_TYPE)
            await resolver.ensure_platform_anchor(
                inverter_platform,
                f"{inverter_platform.issuer_id}_s1_origin_anchor",
                [INVERTER_TYPE],
            )
            await resolver.migrate_platform(inverter_platform.issuer_id, inverter_platform)

            successor_platform = await _ensure_successor_platform(
                fed_client,
                factory_url,
                inverter_platform,
                INVERTER_TYPE,
            )
            reporter.record_observation(
                (
                    f"Routes prepared: {pv_platform.issuer_id}->{pv_platform.platform_id}, "
                    f"{inverter_platform.issuer_id}->{inverter_platform.platform_id}; "
                    f"successor {successor_platform.platform_id} registered as import target"
                ),
                True,
            )

        try:
            if resolver is None or pv_platform is None or inverter_platform is None or successor_platform is None:
                with reporter.step(
                    "Abort after setup failure",
                    "Scenario stops before issuing DPPs when federation setup did not complete",
                ):
                    reporter.record_observation("Setup did not complete; see the failed setup step above", False)
                raise _S1SetupFailed("Setup failed")

            inverter_id = f"{inverter_platform.issuer_id}-s1-inv-001"
            installation_id = f"{pv_platform.issuer_id}-s1-pv-001"

            with reporter.step(
                "Issue initial inverter and installation DPPs",
                "Installation contains one hard and one soft reference to inverter revision 1",
            ):
                async with PlatformClient(inverter_platform) as inverter_client:
                    await inverter_client.ensure_subject_type(INVERTER_TYPE)
                    inverter_v1 = await inverter_client.issue_dpp(
                        IssueDppSpec(
                            dpp_id=inverter_id,
                            schema_version=DppSchemaVersion(
                                subject_type=INVERTER_TYPE,
                                major_version=1,
                                minor_version=0,
                            ),
                            dpp_payload=_inverter_payload("1.0"),
                        )
                    )

                async with PlatformClient(pv_platform) as pv_client:
                    await pv_client.ensure_subject_type(INSTALLATION_TYPE)
                    installation_v1 = await pv_client.issue_dpp(
                        IssueDppSpec(
                            dpp_id=installation_id,
                            schema_version=DppSchemaVersion(
                                subject_type=INSTALLATION_TYPE,
                                major_version=1,
                                minor_version=0,
                            ),
                            dpp_payload=_installation_payload(inverter_id, inverter_v1.version),
                        )
                    )

                hard_v1, initial_hard_target = await _resolve_hard(
                    resolver,
                    INVERTER_TYPE,
                    inverter_id,
                    1,
                    inverter_platform,
                )
                soft_v1, _ = await _resolve_soft_current(
                    resolver,
                    INVERTER_TYPE,
                    inverter_id,
                    inverter_platform,
                )
                success = (
                    inverter_v1.version == 1
                    and installation_v1.version == 1
                    and hard_v1.version == 1
                    and soft_v1["version"] == 1
                )
                reporter.record_observation(
                    f"Hard ref -> inverter v{hard_v1.version}; soft ref -> inverter v{soft_v1['version']}",
                    success,
                    {
                        "installation_hash": installation_v1.payload_hash,
                        "hard_target": initial_hard_target,
                    },
                )

            with reporter.step(
                "Evolve target inverter DPP",
                "Hard reference remains pinned to revision 1; soft reference resolves to revision 2",
            ):
                if inverter_v1 is None or installation_v1 is None:
                    raise RuntimeError("Initial DPPs were not issued")
                async with PlatformClient(inverter_platform) as inverter_client:
                    inverter_v2 = await inverter_client.revise_dpp(
                        inverter_id,
                        ReviseDppSpec(
                            schema_version=DppSchemaVersion(
                                subject_type=INVERTER_TYPE,
                                major_version=1,
                                minor_version=0,
                            ),
                            dpp_payload=_inverter_payload("2.0"),
                        ),
                    )

                hard_after_evolution, _ = await _resolve_hard(
                    resolver,
                    INVERTER_TYPE,
                    inverter_id,
                    1,
                    inverter_platform,
                )
                soft_after_evolution, _ = await _resolve_soft_current(
                    resolver,
                    INVERTER_TYPE,
                    inverter_id,
                    inverter_platform,
                )
                current_installation = await _get_revision(pv_platform, installation_id, 1)
                success = (
                    inverter_v2.version == 2
                    and hard_after_evolution.version == 1
                    and soft_after_evolution["version"] == 2
                    and current_installation.payload_hash == installation_v1.payload_hash
                    and current_installation.dpp_payload == installation_v1.dpp_payload
                )
                reporter.record_observation(
                    (
                        f"Target evolved to v{inverter_v2.version}; hard ref stayed v{hard_after_evolution.version}; "
                        f"soft ref moved to v{soft_after_evolution['version']}; installation hash unchanged"
                    ),
                    success,
                )

            with reporter.step(
                "Import inverter revisions into successor platform and migrate issuer route",
                "Resolver route for inverter issuer changes to Platform C without changing reference values",
            ):
                if inverter_v1 is None or inverter_v2 is None or installation_v1 is None:
                    raise RuntimeError("Target revisions were not prepared")
                async with PlatformClient(successor_platform) as successor_client:
                    await successor_client.ensure_subject_type(INVERTER_TYPE)
                    await successor_client.cache_schema(INVERTER_TYPE)
                    await successor_client.import_revisions([inverter_v1, inverter_v2])

                migration = await resolver.migrate_platform(inverter_platform.issuer_id, successor_platform)
                current_installation = await _get_revision(pv_platform, installation_id, 1)
                success = (
                    migration.get("issuer_id", migration.get("issuerId")) == inverter_platform.issuer_id
                    and migration.get("platform") == successor_platform.platform_id
                    and current_installation.payload_hash == installation_v1.payload_hash
                    and current_installation.dpp_payload == installation_v1.dpp_payload
                )
                reporter.record_observation(
                    f"Migrated {inverter_platform.issuer_id} to {successor_platform.platform_id}; installation unchanged",
                    success,
                    {"migration": migration},
                )

            with reporter.step(
                "Resolve references after issuer migration",
                "Hard reference resolves to v1 and soft reference resolves to current v2 through successor platform",
            ):
                if installation_v1 is None:
                    raise RuntimeError("Installation was not issued")
                hard_after_migration, migrated_hard_target = await _resolve_hard(
                    resolver,
                    INVERTER_TYPE,
                    inverter_id,
                    1,
                    successor_platform,
                )
                soft_after_migration, migrated_soft_target = await _resolve_soft_current(
                    resolver,
                    INVERTER_TYPE,
                    inverter_id,
                    successor_platform,
                )
                current_installation = await _get_revision(pv_platform, installation_id, 1)
                references_unchanged = current_installation.dpp_payload == installation_v1.dpp_payload
                success = (
                    hard_after_migration.version == 1
                    and soft_after_migration["version"] == 2
                    and migrated_hard_target != initial_hard_target
                    and references_unchanged
                    and current_installation.payload_hash == installation_v1.payload_hash
                )
                reporter.record_observation(
                    (
                        f"After migration hard -> v{hard_after_migration.version}, "
                        f"soft -> v{soft_after_migration['version']}, route changed to {migrated_hard_target}"
                    ),
                    success,
                    {"soft_target": migrated_soft_target},
                )

            with reporter.step(
                "Pause original inverter platform and resolve again",
                "Resolution no longer depends on the old physical hosting platform",
            ):
                await fed_client.pause_platform(factory_url, inverter_platform.platform_id)
                try:
                    hard_without_old, _ = await _resolve_hard(
                        resolver,
                        INVERTER_TYPE,
                        inverter_id,
                        1,
                        successor_platform,
                    )
                    soft_without_old, _ = await _resolve_soft_current(
                        resolver,
                        INVERTER_TYPE,
                        inverter_id,
                        successor_platform,
                    )
                    reporter.record_observation(
                        (
                            f"Original platform paused; hard -> v{hard_without_old.version}, "
                            f"soft -> v{soft_without_old['version']} from successor"
                        ),
                        hard_without_old.version == 1 and soft_without_old["version"] == 2,
                    )
                finally:
                    await fed_client.resume_platform(factory_url, inverter_platform.platform_id)

        except _S1SetupFailed:
            pass
        finally:
            if resolver is not None and inverter_platform is not None:
                with reporter.step(
                    "Restore inverter issuer route",
                    "Resolver route points back to the original inverter platform for later scenarios",
                ):
                    try:
                        restored = await resolver.migrate_platform(inverter_platform.issuer_id, inverter_platform)
                        reporter.record_observation(
                            f"Restored {inverter_platform.issuer_id} to {inverter_platform.platform_id}",
                            restored.get("platform") == inverter_platform.platform_id,
                        )
                    except Exception as exc:
                        reporter.record_observation(f"Could not restore route: {exc}", False)

    report_path = reporter.finalize()
    logger.info("s1_complete", report_path=str(report_path))
    return reporter.result.outcome == "PASSED"


def _inverter_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://dpp.example.org/schemas/s1-inverter",
        "title": "S1 Inverter",
        "type": "object",
        "properties": {
            "serialNumber": {"type": "string"},
            "manufacturer": {"type": "string"},
            "ratedPowerKw": {"type": "number"},
            "firmwareVersion": {"type": "string"},
        },
        "required": ["serialNumber", "manufacturer", "ratedPowerKw", "firmwareVersion"],
        "additionalProperties": False,
    }


def _installation_schema() -> dict:
    ref_pattern = f"^{INVERTER_TYPE}/[^/]+$"
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://dpp.example.org/schemas/s1-pv-installation",
        "title": "S1 PV Installation",
        "type": "object",
        "properties": {
            "installationId": {"type": "string"},
            "site": {"type": "string"},
            "inverterEvidenceRef": {
                "type": "object",
                "x-dpp-reference": INVERTER_TYPE,
                "properties": {
                    "$ref": {"type": "string", "pattern": ref_pattern},
                    "version": {"type": "integer", "minimum": 1},
                    "mode": {"const": "hard"},
                },
                "required": ["$ref", "version", "mode"],
                "additionalProperties": False,
            },
            "inverterCurrentRef": {
                "type": "object",
                "properties": {
                    "$ref": {"type": "string", "pattern": ref_pattern},
                    "mode": {"const": "soft"},
                },
                "required": ["$ref", "mode"],
                "additionalProperties": False,
            },
        },
        "required": ["installationId", "site", "inverterEvidenceRef", "inverterCurrentRef"],
        "additionalProperties": False,
    }


def _inverter_payload(firmware_version: str) -> dict:
    return {
        "serialNumber": "INV-001",
        "manufacturer": "InverterCo",
        "ratedPowerKw": 10,
        "firmwareVersion": firmware_version,
    }


def _installation_payload(inverter_id: str, hard_version: int) -> dict:
    ref = f"{INVERTER_TYPE}/{inverter_id}"
    return {
        "installationId": "PV-001",
        "site": "Demo Site",
        "inverterEvidenceRef": {
            "$ref": ref,
            "version": hard_version,
            "mode": "hard",
        },
        "inverterCurrentRef": {
            "$ref": ref,
            "mode": "soft",
        },
    }


async def _ensure_successor_platform(
    fed_client: FederationClient,
    factory_url: str,
    source_platform: PlatformInfo,
    subject_type: str,
) -> PlatformInfo:
    successor_issuer_prefix = f"{source_platform.issuer_id}_s1_successor"
    platforms = await fed_client.list_platforms(factory_url)
    for platform in _s1_successor_candidates(platforms, successor_issuer_prefix, subject_type):
        if platform.status == PlatformStatus.PAUSED:
            await fed_client.resume_platform(factory_url, platform.platform_id)
        if await _wait_for_revision_import(platform, attempts=3, delay_seconds=1.0):
            return platform
        logger.warning(
            "s1_successor_missing_import_endpoint",
            platform_id=platform.platform_id,
            stack=platform.stack,
        )

    last_created: PlatformInfo | None = None
    for stack in _successor_stack_order(source_platform.stack):
        successor = await fed_client.create_platform(
            factory_url,
            stack=stack,
            issuer_id=_next_successor_issuer(successor_issuer_prefix, platforms),
            subject_types=[subject_type],
        )
        platforms.append(successor)
        last_created = successor
        if await _wait_for_revision_import(successor, attempts=12, delay_seconds=1.0):
            return successor
        logger.warning(
            "s1_created_successor_missing_import_endpoint",
            platform_id=successor.platform_id,
            stack=successor.stack,
        )

    if last_created is None:
        raise RuntimeError("Could not prepare a successor platform for S1")
    raise RuntimeError(
        "Could not prepare an import-capable successor platform for S1. "
        "Rebuild platform images so /admin/import-revisions is available before rerunning the scenario."
    )


def _s1_successor_candidates(
    platforms: list[PlatformInfo],
    issuer_prefix: str,
    subject_type: str,
) -> list[PlatformInfo]:
    """Return existing S1 successors without confusing them with source platforms."""
    return [
        platform
        for platform in platforms
        if platform.issuer_id.startswith(issuer_prefix) and subject_type in platform.subject_types
    ]


def _successor_stack_order(source_stack: str) -> list[str]:
    """Try the opposite implementation first, then the source stack as a fallback."""
    opposite = "spring-postgres" if source_stack != "spring-postgres" else "fastapi-mongo"
    stacks = [opposite, source_stack]
    return list(dict.fromkeys(stacks))


def _next_successor_issuer(issuer_prefix: str, platforms: list[PlatformInfo]) -> str:
    """Choose a unique resolver-registration alias for a migration successor."""
    used_issuers = {platform.issuer_id for platform in platforms}
    if issuer_prefix not in used_issuers:
        return issuer_prefix

    index = 2
    while f"{issuer_prefix}_{index}" in used_issuers:
        index += 1
    return f"{issuer_prefix}_{index}"


async def _supports_revision_import(platform: PlatformInfo) -> bool:
    async with PlatformClient(platform) as client:
        return await client.supports_revision_import()


async def _wait_for_revision_import(
    platform: PlatformInfo,
    *,
    attempts: int,
    delay_seconds: float,
) -> bool:
    """Wait for a freshly spawned S1 successor to expose the revision-import endpoint.

    Factory creation waits for container health, but live e2e runs can still hit a
    short window where the app accepts health checks before the admin route is
    reachable. A definitive 404 still means the image is stale and should not be
    reused; transient HTTP failures are retried for the newly created successor.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await _supports_revision_import(platform)
        except httpx.HTTPError as exc:
            logger.warning(
                "s1_successor_import_probe_retry",
                platform_id=platform.platform_id,
                attempt=attempt,
                attempts=attempts,
                error=str(exc),
            )
            if attempt == attempts:
                return False
            await asyncio.sleep(delay_seconds)
    return False


async def _get_revision(platform: PlatformInfo, dpp_id: str, version: int) -> DppResponse:
    async with PlatformClient(platform) as client:
        return await client.get_revision(dpp_id, version)


async def _resolve_hard(
    resolver: ResolverClient,
    subject_type: str,
    dpp_id: str,
    version: int,
    platform: PlatformInfo,
) -> tuple[DppResponse, str]:
    target_url, data = await _resolve_and_fetch(resolver, subject_type, dpp_id, version, platform)
    return DppResponse.model_validate(data), target_url


async def _resolve_soft_current(
    resolver: ResolverClient,
    subject_type: str,
    dpp_id: str,
    platform: PlatformInfo,
) -> tuple[dict, str]:
    target_url, data = await _resolve_and_fetch(resolver, subject_type, dpp_id, None, platform)
    revisions = data.get("revisions", [])
    if not revisions:
        raise RuntimeError(f"Soft resolution returned no revisions for {dpp_id}")
    return max(revisions, key=lambda revision: revision["version"]), target_url


async def _resolve_and_fetch(
    resolver: ResolverClient,
    subject_type: str,
    dpp_id: str,
    version: int | None,
    platform: PlatformInfo,
) -> tuple[str, dict]:
    target_url = await resolver.resolve(subject_type, dpp_id, version)
    parsed_target = urlparse(target_url)
    fetch_url = f"{platform.external_url.rstrip('/')}{parsed_target.path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(fetch_url)
    response.raise_for_status()
    return target_url, copy.deepcopy(response.json())
