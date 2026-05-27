from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DppSchemaDTO(BaseModel):
    # validation_alias accepts both camelCase (from resolver) and snake_case (from MongoDB)
    # using populate_by_name; serialization uses snake_case field names.
    model_config = ConfigDict(populate_by_name=True)

    subject_type: str = Field(validation_alias="subjectType")
    major_version: int = Field(validation_alias="majorVersion")
    minor_version: int = Field(validation_alias="minorVersion")
    schema_document: dict = Field(validation_alias="schemaDocument")
    published_at: datetime = Field(validation_alias="publishedAt", default=None)

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
