"""Keyword subscription pagination."""

from pydantic import Field

from schema.common import ApiModel


class KeywordSubscriptionParams(ApiModel):
    page: int = Field(default=0, ge=0)
    size: int = Field(default=20, ge=1, le=100)
