"""Profile contracts share the authenticated user's private response fields."""

from typing import Annotated

from pydantic import BeforeValidator

from schema.auth import AuthUserResponse
from schema.common import ApiModel, Language


class UpdateProfileRequest(ApiModel):
    language: Annotated[
        Language,
        BeforeValidator(lambda value: value.strip() if isinstance(value, str) else value),
    ]


class ProfileResponse(AuthUserResponse):
    """Only expose this response to its owner."""
