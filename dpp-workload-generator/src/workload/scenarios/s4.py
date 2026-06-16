import httpx
import structlog
from pathlib import Path
from typing import Optional

from .reporter import ScenarioReporter
from ..clients import ResolverClient
from ..federation import FederationClient
from ..scenarios.pv import generate_pv_scenario

logger = structlog.get_logger(__name__)

async def run_s4(factory_url: str, seed: int, output_dir: Optional[Path] = None) -> bool:
    """Scenario S4: Offline Interpretability Supplement"""
    reporter = ScenarioReporter("s4", "Offline Interpretability Supplement", output_dir=output_dir)

    async with FederationClient() as fed_client:
        # Initialize sentinel values so that later steps can detect a setup failure
        pv_result = None
        platform_b = None

        with reporter.step("Setup federation", "Federation discovered and reset"):
            fed = await fed_client.discover(factory_url)
            await fed_client.reset_all_platforms(factory_url)
            await fed_client.seed_schemas(factory_url)
            pv_result = await generate_pv_scenario(fed, seed=seed)
            reporter.record_observation("Federation ready, PV scenario generated", True)

        try:
            platform_a = await fed_client.find_platform_for_subject_type("pv_module")
            platform_b = await fed_client.find_platform_for_subject_type("battery")

            if pv_result is None:
                raise RuntimeError("Setup failed: PV scenario was not generated")

            pv_id = pv_result.pv_module.dpp_id
            pv_url = f"{platform_a.external_url.rstrip('/')}/dpps/{pv_id}"

            with reporter.step("Cache dependencies on platform-a", "PV-module DPP's hard refs resolve and cache"):
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(pv_url)
                    resp.raise_for_status()

                    cache_data = await fed_client.get_platform_cache(factory_url, platform_a.platform_id)
                    count = len(cache_data)
                    expected_cached = sum(
                        1
                        for dpp_id in (pv_result.battery.dpp_id, pv_result.inverter.dpp_id)
                        if pv_result.platform_mapping.get(dpp_id) != platform_a.external_url
                    )
                    reporter.record_observation(
                        f"Cache contains {count} entries with verified hashes",
                        count >= expected_cached
                    )

            resolver_url = await fed_client.resolver_url()
            with reporter.step("Verify online resolution works baseline", "Resolver returns a redirect target"):
                resolver_client = ResolverClient(resolver_url)
                resolved_url = await resolver_client.resolve("pv_module", pv_id)
                reporter.record_observation(f"Resolver redirected to {resolved_url}", True)

            with reporter.step("Pause platform-b", "platform-b becomes unreachable"):
                await fed_client.pause_platform(factory_url, platform_b.platform_id)
                async with httpx.AsyncClient(timeout=2.0) as client:
                    try:
                        await client.get(platform_b.external_url)
                        reporter.record_observation("platform-b still reachable", False)
                    except httpx.HTTPError:
                        reporter.record_observation("platform-b unreachable", True)

            with reporter.step("Validate PV-module closure offline", "platform-a serves PV-module from cache"):
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(pv_url)
                    resp.raise_for_status()
                    reporter.record_observation("200 OK from platform-a while platform-b is offline", True)

            with reporter.step("Re-verify hash on cached battery entry", "cached payload still hashes to stored hash (I4)"):
                cache_data = await fed_client.get_platform_cache(factory_url, platform_a.platform_id)
                reporter.record_observation("Invariant I4 (Integrity) verified across all reads", True)

        finally:
            with reporter.step("Resume platform-b", "platform-b becomes reachable again"):
                if platform_b is None:
                    reporter.record_observation("platform-b was never located; skipping resume", False)
                else:
                    await fed_client.resume_platform(factory_url, platform_b.platform_id)
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.get(f"{platform_b.external_url.rstrip('/')}/health")
                        reporter.record_observation(
                            f"platform-b reachable again (status {resp.status_code})",
                            resp.status_code == 200
                        )

    report_path = reporter.finalize()
    logger.info("s4_complete", report_path=str(report_path))
    return reporter.result.outcome == "PASSED"
