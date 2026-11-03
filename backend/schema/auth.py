"""Auth DTOs from docs/api/01-auth.md. Wire field names use camelCase."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, EmailStr, Field, StrictBool, StrictInt, StrictStr, field_serializer

from .common import Affiliation, ApiModel, Language, Role


class MockLoginRequest(ApiModel):
    mock_account_id: Annotated[
        StrictStr, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    ]


class CsrfTokenResponse(ApiModel):
    csrf_token: str
    header_name: Literal["X-CSRF-Token"]


class MockAccountSummary(ApiModel):
    mock_account_id: str
    display_name: str
    affiliation: Affiliation
    role: Role


class MockAccountListResponse(ApiModel):
    accounts: list[MockAccountSummary]


class AuthUserResponse(ApiModel):
    user_id: UUID
    name: str
    email: EmailStr
    affiliation: Affiliation
    role: Role
    language: Language


class SessionInfo(ApiModel):
    idle_timeout_seconds: Annotated[StrictInt, Field(gt=0)]
    idle_expires_at: AwareDatetime
    absolute_expires_at: AwareDatetime

    @field_serializer("idle_expires_at", "absolute_expires_at")
    def serialize_expiry(self, value: datetime) -> str:
        return value.astimezone(ZoneInfo("Asia/Seoul")).isoformat()


class LoginResponse(ApiModel):
    user: AuthUserResponse
    is_new_user: StrictBool
    session: SessionInfo
    csrf_token: str
