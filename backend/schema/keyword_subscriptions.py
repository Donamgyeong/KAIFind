"""Private keyword subscription API models."""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import StrictStr, field_serializer, field_validator

from schema.common import ApiModel


class CreateKeywordSubscriptionRequest(ApiModel):
    keyword: StrictStr

    @field_validator('keyword')
    @classmethod
    def validate_keyword(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 50:
            raise ValueError('keyword must contain 1 to 50 characters')
        return value


class KeywordSubscriptionResponse(ApiModel):
    subscription_id: UUID
    keyword: str
    created_at: datetime

    @field_serializer('created_at')
    def serialize_time(self, value):
        return value.astimezone(ZoneInfo('Asia/Seoul')).isoformat()


class KeywordSubscriptionPage(ApiModel):
    items: list[KeywordSubscriptionResponse]
    page: int
    size: int
    total_elements: int
    total_pages: int
