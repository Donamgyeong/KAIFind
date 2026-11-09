"""Collection request and public response contracts."""

from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, StrictBool, field_serializer, field_validator

from schema.common import ApiModel


class CollectRequest(ApiModel):
    confirmed_ownership: StrictBool

    @field_validator('confirmed_ownership')
    @classmethod
    def require_confirmation(cls, value):
        if not value:
            raise ValueError('Ownership must be confirmed')
        return value


class CollectionResponse(ApiModel):
    collection_id: UUID
    item_id: UUID
    collector_id: UUID
    collected_at: AwareDatetime
    status: Literal['COLLECTED'] = 'COLLECTED'

    @field_serializer('collected_at')
    def serialize_time(self, value):
        return value.astimezone(ZoneInfo('Asia/Seoul')).isoformat()
