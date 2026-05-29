import typer
import asyncio
import time
from pathlib import Path
import structlog
from typing import Optional, List
from .federation import FederationClient
from .measurement import MeasurementRecorder, measure_operation
from .scenarios.depth import generate_depth_chain
from .scenarios.fanout import generate_fanout
from .scenarios.pv import generate_pv_scenario
from .scenarios.schema_evolution import run_schema_evolution
from .scenarios.s1 import run_s1
from .scenarios.s2 import run_s2
from .scenarios.s3 import run_s3
from .clients import ResolverClient, PlatformClient, IssueDppSpec, DppSchemaVersion
from .payloads import generate_valid_payload, generate_dpp_id
from .schemas.generator import generate_schema
import httpx

app = typer.Typer(help="DPP Workload Generator")
logger = structlog.get_logger(__name__)

@app.callback()
def callback():
    """
    DPP Workload Generator CLI
    """
    pass

@app.command()
def measure(
    workload: str = typer.Option(..., "--workload", help="Workload kind: depth, fanout, issue, resolve, query"),
    range_str: str = typer.Option("1-10", "--range", help="Parameter range (e.g. 1-10)"),
    runs: int = typer.Option(5, "--runs", help="Number of measurement runs per value"),
    warmup_runs: int = typer.Option(1, "--warmup-runs", help="Number of warmup runs (not recorded)"),
    output: Optional[str] = typer.Option(None, "--output", help="Output path for CSV"),
    seed: int = typer.Option(42, "--seed", help="Random seed"),
    factory_url: str = typer.Option("http://localhost:8000", "--factory-url", help="Factory URL")
):
    """Run a parameterized measurement."""
    asyncio.run(_run_measure(workload, range_str, runs, warmup_runs, output, seed, factory_url))

async def _resolve_recursive(resolver: ResolverClient, subject_type: str, dpp_id: str, version: Optional[int] = None):
    """Helper for depth traversal."""
    final_url = await resolver.resolve(subject_type, dpp_id, version)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(final_url)
        resp.raise_for_status()
        data = resp.json()
        
        # Extract hard dependencies from payload
        payload = data.get("dpp_payload", {})
        dependencies = payload.get("dependencies", [])
        
        tasks = []
        for dep in dependencies:
            if "version" in dep: # HARD ref
                ref_str = dep["$ref"]
                parts = ref_str.split("/")
                if len(parts) == 2:
                    st, did = parts
                    tasks.append(_resolve_recursive(resolver, st, did, dep["version"]))
        
        if tasks:
            await asyncio.gather(*tasks)

async def _run_measure(workload: str, range_str: str, runs: int, warmup_runs: int, 
                       output: Optional[str], seed: int, factory_url: str):
    # Parse range
    if "-" in range_str:
        start_val, end_val = map(int, range_str.split("-"))
        param_values = list(range(start_val, end_val + 1))
    else:
        param_values = [int(range_str)]

    recorder = MeasurementRecorder(output_dir=output)
    recorder.start_run(f"run-{int(time.time())}", workload)
    
    async with FederationClient() as fed_client:
        # 1. Discover
        fed = await fed_client.discover(factory_url)
        resolver = ResolverClient(fed.resolver.external_url)
        
        for val in param_values:
            for run_idx in range(warmup_runs + runs):
                is_warmup = run_idx < warmup_runs
                run_seed = seed + val * 100 + run_idx
                
                # 2. Reset between runs
                await fed_client.reset_all_platforms(factory_url)
                
                logger.info("run_start", workload=workload, value=val, run=run_idx, is_warmup=is_warmup)
                
                try:
                    if workload == "depth":
                        # Setup
                        result = await generate_depth_chain(fed, val, seed=run_seed)
                        # Measure
                        async with measure_operation(recorder, "resolve_root_closure", val, warmup=is_warmup) as ctx:
                            await _resolve_recursive(resolver, result.root_subject_type, result.root_dpp_id)
                            
                    elif workload == "fanout":
                        # Setup
                        result = await generate_fanout(fed, val, seed=run_seed)
                        # Measure
                        async with measure_operation(recorder, "resolve_all_children", val, warmup=is_warmup) as ctx:
                            await asyncio.gather(*[
                                resolver.resolve(c.schema_version.subject_type, c.dpp_id)
                                for c in result.children
                            ])
                            
                    elif workload == "issue":
                        p_info = fed.platforms[0]
                        st = "simple_dpp"
                        await resolver.publish_schema(st, 1, 0, generate_schema(st))
                        spec = IssueDppSpec(
                            schema_version=DppSchemaVersion(subject_type=st, major_version=1, minor_version=0),
                            dpp_payload=generate_valid_payload({}, seed=run_seed)
                        )
                        async with measure_operation(recorder, "issue_simple", val, warmup=is_warmup) as ctx:
                            async with PlatformClient(p_info) as client:
                                await client.issue_dpp(spec)
                                ctx.bytes_payload = len(spec.model_dump_json())
                                
                    elif workload == "resolve":
                        p_info = fed.platforms[0]
                        st = "simple_dpp"
                        await resolver.publish_schema(st, 1, 0, generate_schema(st))
                        async with PlatformClient(p_info) as client:
                            resp = await client.issue_dpp(IssueDppSpec(
                                schema_version=DppSchemaVersion(subject_type=st, major_version=1, minor_version=0),
                                dpp_payload=generate_valid_payload({}, seed=run_seed)
                            ))
                        async with measure_operation(recorder, "resolve_single", val, warmup=is_warmup) as ctx:
                            await resolver.resolve(st, resp.dpp_id)
                            
                    elif workload == "query":
                        logger.warning("query_workload_skipped", reason="P-9 projection not implemented")
                    else:
                        logger.error("unknown_workload", workload=workload)
                        break
                except Exception as e:
                    logger.error("run_failed", error=str(e))
                    if not is_warmup:
                        # Recording of failure happens in measure_operation's finally block
                        pass
    
    csv_path = recorder.end_run()
    typer.echo(f"Results written to {csv_path}")

@app.command()
def generate_depth(
    depth: int = typer.Option(..., "--depth", help="Depth of the chain"),
    seed: int = typer.Option(42, "--seed", help="Random seed"),
    factory_url: str = typer.Option("http://localhost:8000", "--factory-url", help="Factory URL")
):
    """Generate a depth chain fixture."""
    try:
        asyncio.run(_run_generate_depth(depth, seed, factory_url))
    except Exception as e:
        logger.error("generate_depth_failed", error=str(e))
        raise typer.Exit(code=1)

async def _run_generate_depth(depth: int, seed: int, factory_url: str):
    async with FederationClient() as fed_client:
        fed = await fed_client.discover(factory_url)
        result = await generate_depth_chain(fed, depth, seed=seed)
        typer.echo(f"Created depth chain (depth={depth})")
        typer.echo(f"Root DPP: {result.root_subject_type}/{result.root_dpp_id}")
        for dpp in result.chain:
             typer.echo(f"  - {dpp.schema_version.subject_type}/{dpp.dpp_id} on {result.platform_mapping[dpp.dpp_id]}")

@app.command()
def generate_fanout(
    fanout: int = typer.Option(..., "--fanout", help="Number of children"),
    root_platform: Optional[str] = typer.Option(None, "--root-platform", help="Root platform ID"),
    seed: int = typer.Option(42, "--seed", help="Random seed"),
    factory_url: str = typer.Option("http://localhost:8000", "--factory-url", help="Factory URL")
):
    """Generate a fan-out fixture."""
    try:
        asyncio.run(_run_generate_fanout(fanout, root_platform, seed, factory_url))
    except Exception as e:
        logger.error("generate_fanout_failed", error=str(e))
        raise typer.Exit(code=1)

async def _run_generate_fanout(fanout: int, root_platform: Optional[str], seed: int, factory_url: str):
    async with FederationClient() as fed_client:
        fed = await fed_client.discover(factory_url)
        result = await generate_fanout(fed, fanout, root_platform_id=root_platform, seed=seed)
        typer.echo(f"Created fan-out (fanout={fanout})")
        typer.echo(f"Parent DPP: {result.parent_dpp.schema_version.subject_type}/{result.parent_dpp.dpp_id} on {result.platform_mapping[result.parent_dpp.dpp_id]}")
        typer.echo(f"Children:")
        for child in result.children:
             typer.echo(f"  - {child.schema_version.subject_type}/{child.dpp_id} on {result.platform_mapping[child.dpp_id]}")

@app.command()
def pv_scenario(
    seed: int = typer.Option(42, "--seed", help="Random seed"),
    factory_url: str = typer.Option("http://localhost:8000", "--factory-url", help="Factory URL")
):
    """Generate the PV/battery/inverter scenario."""
    try:
        asyncio.run(_run_pv_scenario(seed, factory_url))
    except Exception as e:
        logger.error("pv_scenario_failed", error=str(e))
        raise typer.Exit(code=1)

async def _run_pv_scenario(seed: int, factory_url: str):
    async with FederationClient() as fed_client:
        fed = await fed_client.discover(factory_url)
        result = await generate_pv_scenario(fed, seed=seed)
        typer.echo("Created PV scenario")
        typer.echo(f"PV Module: {result.pv_module.dpp_id} on {result.platform_mapping[result.pv_module.dpp_id]}")
        typer.echo(f"Battery:   {result.battery.dpp_id} on {result.platform_mapping[result.battery.dpp_id]}")
        typer.echo(f"Inverter:  {result.inverter.dpp_id} on {result.platform_mapping[result.inverter.dpp_id]}")

@app.command()
def schema_evolution(
    revisions: int = typer.Option(5, "--revisions", help="Number of revisions before update"),
    update_kind: str = typer.Option("minor", "--update-kind", help="Update kind: minor or major"),
    seed: int = typer.Option(42, "--seed", help="Random seed"),
    output: Optional[str] = typer.Option(None, "--output", help="Output path for CSV"),
    factory_url: str = typer.Option("http://localhost:8000", "--factory-url", help="Factory URL")
):
    """Measure the impact of schema evolution."""
    try:
        asyncio.run(_run_schema_evolution(revisions, update_kind, seed, output, factory_url))
    except Exception as e:
        logger.error("schema_evolution_failed", error=str(e))
        raise typer.Exit(code=1)

async def _run_schema_evolution(revisions: int, update_kind: str, seed: int, output: Optional[str], factory_url: str):
    recorder = MeasurementRecorder(output_dir=output)
    recorder.start_run(f"run-{int(time.time())}", f"schema-evolution-{update_kind}")
    async with FederationClient() as fed_client:
        fed = await fed_client.discover(factory_url)
        await fed_client.reset_all_platforms(factory_url)
        await run_schema_evolution(fed, revisions, update_kind, recorder, seed=seed)
    
    csv_path = recorder.end_run()
    typer.echo(f"Results written to {csv_path}")

scenario_app = typer.Typer(help="Execute federation scenarios (S1, S2)")
app.add_typer(scenario_app, name="scenario")

@scenario_app.command()
def s1(
    factory_url: str = typer.Option("http://localhost:8000", "--factory-url"),
    seed: int = typer.Option(42, "--seed"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir")
):
    """Scenario S1: Offline Interpretability"""
    try:
        success = asyncio.run(run_s1(factory_url, seed, output_dir))
        if not success:
            raise typer.Exit(code=1)
    except Exception as e:
        logger.error("s1_failed", error=str(e))
        raise typer.Exit(code=1)

@scenario_app.command()
def s2(
    factory_url: str = typer.Option("http://localhost:8000", "--factory-url"),
    seed: int = typer.Option(42, "--seed"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir")
):
    """Scenario S2: Independent Schema Evolution"""
    try:
        success = asyncio.run(run_s2(factory_url, seed, output_dir))
        if not success:
            raise typer.Exit(code=1)
    except Exception as e:
        logger.error("s2_failed", error=str(e))
        raise typer.Exit(code=1)

@scenario_app.command()
def s3(
    factory_url: str = typer.Option("http://localhost:8000", "--factory-url"),
    seed: int = typer.Option(42, "--seed"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir")
):
    """Scenario S3: Schema-Level Cycle Rejection"""
    try:
        success = asyncio.run(run_s3(factory_url, seed, output_dir))
        if not success:
            raise typer.Exit(code=1)
    except Exception as e:
        logger.error("s3_failed", error=str(e))
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
