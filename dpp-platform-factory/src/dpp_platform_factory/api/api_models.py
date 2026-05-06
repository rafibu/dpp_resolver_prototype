from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
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
    status: PlatformStatus
    created_at: datetime

class ResolverInfo(BaseModel):
    external_url: str
    status: PlatformStatus

class FederationOverview(BaseModel):
    resolver: Optional[ResolverInfo]
    platforms: List[PlatformInfo]

class SeedSchemasRequest(BaseModel):
    schemas: Optional[List[str]] = None

class SeedSchemasSummary(BaseModel):
    loaded: List[str]
    failed: List[str]
