from datetime import datetime

from pydantic import BaseModel, field_validator


class DppSchemaDTO(BaseModel):
    subject_type: str
    major_version: int
    minor_version: int
    schema_document: dict
    published_at: datetime

    @field_validator("major_version")
    @classmethod
    def major_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("major_version must be positive")
        return v

    @field_validator("minor_version")
    @classmethod
    def minor_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("minor_version must be non-negative")
        return v
