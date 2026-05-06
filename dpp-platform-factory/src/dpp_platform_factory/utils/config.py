from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class StackType(str, Enum):
    SPRING_POSTGRES = "spring-postgres"
    FASTAPI_MONGO = "fastapi-mongo"


class ResolverConfig(BaseModel):
    port: int = 8080


class PlatformConfig(BaseModel):
    platform_id: str
    stack: StackType
    issuer_id: str
    subject_types: list[str] = Field(min_length=1)
    port: int
    db_volume: str | None = None

    @model_validator(mode="after")
    def set_default_volume(self) -> "PlatformConfig":
        if self.db_volume is None:
            self.db_volume = f"{self.platform_id}-db"
        return self


class FederationConfig(BaseModel):
    resolver: ResolverConfig = Field(default_factory=ResolverConfig)
    platforms: list[PlatformConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def check_unique_platform_ids(self) -> "FederationConfig":
        seen: set[str] = set()
        for p in self.platforms:
            if p.platform_id in seen:
                raise ValueError(f"Duplicate platform ID: {p.platform_id}")
            seen.add(p.platform_id)
        return self

    @model_validator(mode="after")
    def check_no_port_collisions(self) -> "FederationConfig":
        ports: dict[int, str] = {self.resolver.port: "resolver"}
        for p in self.platforms:
            if p.port in ports:
                raise ValueError(
                    f"Port {p.port} is used by both '{ports[p.port]}' and '{p.platform_id}'"
                )
            ports[p.port] = p.platform_id
        return self


def load_config(path: Path) -> FederationConfig:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return FederationConfig.model_validate(data)
