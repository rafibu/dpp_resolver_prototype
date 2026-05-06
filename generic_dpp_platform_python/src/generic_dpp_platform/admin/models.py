from pydantic import BaseModel


class PlatformConfigDTO(BaseModel):
    platform_name: str | None = None
    base_url: str | None = None
    issuer_id: str | None = None
    resolver_base_url: str | None = None


class SubjectTypeDTO(BaseModel):
    name: str
    description: str | None = None
