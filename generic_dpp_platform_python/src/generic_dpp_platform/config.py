from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str = Field(default="mongodb://localhost:27017", alias="DATABASE_URL")
    mongodb_db_name: str = "dpp_generic_python"
    platform_name: str = Field(default="Generic DPP Platform", alias="PLATFORM_ID")
    base_url: str = "http://localhost:8082"
    issuer_id: str = "gendpp-py"
    resolver_base_url: str = Field(default="http://localhost:8080", alias="RESOLVER_URL")
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
