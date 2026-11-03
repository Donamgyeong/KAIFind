"""Shared API contracts."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, extra="forbid", serialize_by_alias=True
    )


class Role(StrEnum):
    MEMBER = "MEMBER"
    ADMIN = "ADMIN"


class Affiliation(StrEnum):
    STUDENT = "STUDENT"
    FACULTY = "FACULTY"
    STAFF = "STAFF"


class Language(StrEnum):
    KO = "ko"
    EN = "en"


class FieldError(ApiModel):
    field: str
    code: str
    message: str


class ErrorResponse(ApiModel):
    code: str
    message: str
    field_errors: list[FieldError]
