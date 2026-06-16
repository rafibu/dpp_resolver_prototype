import asyncio
import json
import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Dict, List, Optional

from .api_models import (
    FederationOverview,
    LogLine,
    PlatformInfo,
    PlatformSpawnRequest,
    ResolverInfo,
    ScenarioStatus,
    SeedSchemasRequest,
    SeedSchemasSummary,
)
from ..core.platform_service import PlatformService
from ..core.scenario_service import SCENARIO_IDS, ScenarioService
from ..core.schema_seed_service import SchemaSeedService
from ..core.state import FactoryState, PlatformRecord
from ..infrastructure.docker_client import DockerClient
from ..utils.bootstrap import bootstrap
from ..utils.config import load_config
from ..utils.shutdown import shutdown

# Global state / singleton-ish
state: FactoryState = FactoryState()
docker_client: Optional[DockerClient] = None
spawn_lock: asyncio.Lock = asyncio.Lock()
default_platform_ids: set[str] = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    global docker_client, default_platform_ids
    
    if os.getenv("DPP_FACTORY_TESTING") != "true":
        if docker_client is None:
            docker_client = DockerClient()
            
        config_path = Path("default-federation.yml")
        if not config_path.exists():
             config_path = Path("factory/default-federation.yml")
             
        if config_path.exists():
            config = load_config(config_path)
            default_platform_ids.clear()
            default_platform_ids.update({p.platform_id for p in config.platforms})
            await bootstrap(docker_client, config, existing_state=state)
    
    yield
    
    if os.getenv("DPP_FACTORY_KEEP_RUNNING") != "true" and docker_client:
        await shutdown(docker_client, state)

app = FastAPI(title="DPP Factory API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):[0-9]{4}$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# ------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------

def get_docker_client() -> DockerClient:
    global docker_client
    if docker_client is None:
        docker_client = DockerClient()
    return docker_client

def get_platform_service(docker: DockerClient = Depends(get_docker_client)) -> PlatformService:
    return PlatformService(state, docker, spawn_lock, default_platform_ids)

def get_schema_seed_service() -> SchemaSeedService:
    return SchemaSeedService(state)

def get_scenario_service(
    platform_service: PlatformService = Depends(get_platform_service),
    schema_seed_service: SchemaSeedService = Depends(get_schema_seed_service),
) -> ScenarioService:
    return ScenarioService(state, platform_service, schema_seed_service)

def _to_platform_info(record: PlatformRecord) -> PlatformInfo:
    return PlatformInfo(
        platform_id=record.platform_id,
        stack=record.stack,
        issuer_id=record.issuer_id,
        subject_types=record.subject_types,
        external_url=record.external_url,
        internal_url=record.internal_url,
        status=record.status,
        created_at=record.created_at
    )

# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/federation", response_model=FederationOverview)
async def get_federation(service: PlatformService = Depends(get_platform_service)):
    platforms = await service.list_platforms()
    resolver_info = None
    
    resolver = await state.get_resolver()
    if resolver:
        resolver_info = ResolverInfo(
            external_url=resolver.external_url,
            status=resolver.status
        )
            
    return FederationOverview(
        resolver=resolver_info,
        platforms=[_to_platform_info(p) for p in platforms]
    )

@app.get("/platforms", response_model=List[PlatformInfo])
async def list_platforms(service: PlatformService = Depends(get_platform_service)):
    platforms = await service.list_platforms()
    return [_to_platform_info(p) for p in platforms]

@app.post("/platforms", response_model=PlatformInfo)
async def spawn_platform_endpoint(
    req: PlatformSpawnRequest, 
    service: PlatformService = Depends(get_platform_service)
):
    try:
        record = await service.spawn_platform(req.stack, req.issuer_id, req.subject_types)
        return _to_platform_info(record)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503 if "Resolver" in str(e) else 500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/platforms/{platform_id}", response_model=PlatformInfo)
async def get_platform(
    platform_id: str, 
    service: PlatformService = Depends(get_platform_service)
):
    record = await service.get_platform(platform_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Platform {platform_id} not found")
    return _to_platform_info(record)

@app.post("/platforms/{platform_id}/pause", response_model=PlatformInfo)
async def pause_platform(
    platform_id: str, 
    service: PlatformService = Depends(get_platform_service)
):
    try:
        record = await service.pause_platform(platform_id)
        return _to_platform_info(record)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/platforms/{platform_id}/resume", response_model=PlatformInfo)
async def resume_platform(
    platform_id: str, 
    service: PlatformService = Depends(get_platform_service)
):
    try:
        record = await service.resume_platform(platform_id)
        return _to_platform_info(record)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/platforms/{platform_id}/reset", response_model=PlatformInfo)
async def reset_platform(
    platform_id: str, 
    service: PlatformService = Depends(get_platform_service)
):
    try:
        record = await service.reset_platform(platform_id)
        return _to_platform_info(record)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/platforms/{platform_id}")
async def delete_platform(
    platform_id: str, 
    service: PlatformService = Depends(get_platform_service)
):
    try:
        await service.delete_platform(platform_id)
        return {"status": "deleted"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/platforms/{platform_id}/cache", response_model=List[dict])
async def get_platform_cache(
    platform_id: str, 
    service: PlatformService = Depends(get_platform_service)
):
    try:
        return await service.get_platform_cache(platform_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/resolver", response_model=ResolverInfo)
async def get_resolver_info():
    resolver = await state.get_resolver()
    if not resolver:
        return ResolverInfo(external_url="", status="OFFLINE")
    return ResolverInfo(
        external_url=resolver.external_url,
        status=resolver.status
    )

@app.post("/resolver/seed-schemas", response_model=SeedSchemasSummary)
async def seed_schemas(
    req: Optional[SeedSchemasRequest] = None,
    service: SchemaSeedService = Depends(get_schema_seed_service)
):
    try:
        requested = req.schemas if req else None
        return await service.seed_schemas(requested)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503 if "Resolver" in str(e) else 500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _parse_container_logs(raw_logs: bytes) -> List[LogLine]:
    result: List[LogLine] = []
    for raw_line in raw_logs.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            ts = str(parsed.get("timestamp", parsed.get("time", parsed.get("ts", ""))))
            level = str(parsed.get("level", parsed.get("severity", "INFO"))).upper()
            msg = str(parsed.get("message", parsed.get("event", parsed.get("msg", line))))
            extra = {k: v for k, v in parsed.items() if k not in ("timestamp", "time", "ts", "level", "severity", "message", "event", "msg")}
            result.append(LogLine(timestamp=ts, level=level, message=msg, extra=extra))
        except (json.JSONDecodeError, ValueError):
            result.append(LogLine(timestamp="", level="INFO", message=line))
    return result


@app.get("/resolver/logs", response_model=List[LogLine])
async def get_resolver_logs(
    lines: int = 200,
    docker: DockerClient = Depends(get_docker_client),
):
    resolver = await state.get_resolver()
    if not resolver:
        raise HTTPException(status_code=404, detail="Resolver not found")
    try:
        container = docker._client.containers.get(resolver.container_id)
        raw_logs: bytes = container.logs(tail=lines, timestamps=False)
        return _parse_container_logs(raw_logs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/platforms/{platform_id}/logs", response_model=List[LogLine])
async def get_platform_logs(
    platform_id: str,
    lines: int = 200,
    service: PlatformService = Depends(get_platform_service),
    docker: DockerClient = Depends(get_docker_client),
):
    record = await service.get_platform(platform_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Platform {platform_id} not found")
    try:
        container = docker._client.containers.get(record.container_id)
        raw_logs: bytes = container.logs(tail=lines, timestamps=False)
        return _parse_container_logs(raw_logs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_scenario_states: Dict[str, ScenarioStatus] = {}


@app.post("/scenarios/{scenario_id}", response_model=ScenarioStatus)
async def run_scenario(
    scenario_id: str,
    service: ScenarioService = Depends(get_scenario_service),
):
    if scenario_id not in SCENARIO_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_id}")
    status = ScenarioStatus(
        scenario_id=scenario_id,
        status="running",
        steps=[],
        report_md=None,
    )
    _scenario_states[scenario_id] = status
    status = await service.run(scenario_id)
    _scenario_states[scenario_id] = status
    return status


@app.get("/scenarios/{scenario_id}/status", response_model=ScenarioStatus)
async def get_scenario_status(scenario_id: str):
    if scenario_id not in SCENARIO_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_id}")
    if scenario_id not in _scenario_states:
        return ScenarioStatus(
            scenario_id=scenario_id,
            status="pending",
            steps=[],
            report_md=None,
        )
    return _scenario_states[scenario_id]
