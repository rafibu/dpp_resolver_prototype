from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class DependencyType(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"


class DppReference:
    __slots__ = ("subject_type", "dpp_id", "version", "dependency_type", "original_ref", "json_path")

    def __init__(
        self,
        subject_type: str,
        dpp_id: str,
        version: int | None,
        dependency_type: DependencyType,
        original_ref: str,
        json_path: str,
    ) -> None:
        self.subject_type = subject_type
        self.dpp_id = dpp_id
        self.version = version
        self.dependency_type = dependency_type
        self.original_ref = original_ref
        self.json_path = json_path


class DppRevisionSchemaDTO(BaseModel):
    subject_type: str
    major_version: int
    minor_version: int


class DppRevisionRequestDTO(BaseModel):
    dpp_id: str | None = None
    version: int | None = None
    schema_version: DppRevisionSchemaDTO
    dpp_payload: dict


class DppRevisionResponseDTO(BaseModel):
    dpp_id: str
    version: int
    schema_version: DppRevisionSchemaDTO
    dpp_payload: dict
    payload_hash: str
    created_at: datetime


class ApiError(BaseModel):
    error: str
    message: str | None = None
    details: list[str] = []
    timestamp: datetime
    path: str
