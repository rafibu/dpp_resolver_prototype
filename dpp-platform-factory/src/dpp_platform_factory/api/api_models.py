from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from ..core.state import PlatformStatus


class PlatformSpawnRequest(BaseModel):
    stack: str
    issuer_id: str
    subject_types: List[str]

class PlatformInfo(BaseModel):
    platform_id: str
    stack: str
    issuer_id: str
    subject_types: List[str]
    external_url: str
    internal_url: str
    status: PlatformStatus
    created_at: datetime

class ResolverInfo(BaseModel):
    external_url: str
    status: PlatformStatus

class FederationOverview(BaseModel):
    """Observable snapshot of the federated state (Definition 7).

    Consumed by the Frontend and Workload Generator via GET /federation to discover
    the live topology without knowing container details in advance.
    """
    resolver: Optional[ResolverInfo]
    platforms: List[PlatformInfo]

class SeedSchemasRequest(BaseModel):
    schemas: Optional[List[str]] = None

class SeedSchemasSummary(BaseModel):
    loaded: List[str]
    failed: List[str]

class LogLine(BaseModel):
    timestamp: str
    level: str
    message: str
    extra: Dict[str, Any] = Field(default_factory=dict)

class ScenarioStep(BaseModel):
    name: str
    status: str
    error: Optional[str] = None

class ScenarioStatus(BaseModel):
    scenario_id: str
    status: str
    steps: List[ScenarioStep]
    report_md: Optional[str] = None
