from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DppSchemaDTO(BaseModel):
    # Allow both camelCase aliases (from resolver) and snake_case names (from MongoDB)
    model_config = ConfigDict(populate_by_name=True)

    subject_type: str = Field(alias="subjectType")
    major_version: int = Field(alias="majorVersion")
    minor_version: int = Field(alias="minorVersion")
    schema_document: dict = Field(alias="schemaDocument")
    published_at: datetime = Field(alias="publishedAt", default=None)

    @field_validator("major_version", mode="before")
    @classmethod
    def major_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("major_version must be positive")
        return v

    @field_validator("minor_version", mode="before")
    @classmethod
    def minor_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("minor_version must be non-negative")
        return v
