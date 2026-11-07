"""Member-facing collection dispute contracts."""

from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AfterValidator, AwareDatetime, Field, StrictStr, field_serializer

from schema.common import ApiModel


def trim_reason(value):
    return value.strip()


Reason = Annotated[
    StrictStr, AfterValidator(trim_reason), Field(min_length=1, max_length=1000),
]


class CreateDisputeRequest(ApiModel):
    reason: Reason


class DisputeResponse(ApiModel):
    dispute_id: UUID
    item_id: UUID
    collection_id: UUID
    reason: str
    status: Literal['OPEN', 'RESOLVED']
    decision: Literal['UPHELD', 'DISMISSED'] | None
    created_at: AwareDatetime
    resolved_at: AwareDatetime | None

    @field_serializer('created_at', 'resolved_at')
    def serialize_time(self, value):
        return value.astimezone(ZoneInfo('Asia/Seoul')).isoformat() if value else None


class DisputePage(ApiModel):
    items: list[DisputeResponse]
    page: int
    size: int
    total_elements: int
    total_pages: int
