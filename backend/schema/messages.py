"""Item conversation and plain-text message contracts."""

from datetime import datetime
from typing import Annotated, Generic, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AfterValidator, ConfigDict, Field, StrictStr, field_serializer

from schema.common import ApiModel


def trim_content(value):
    return value.strip()


Content = Annotated[
    StrictStr, AfterValidator(trim_content), Field(min_length=1, max_length=2000),
]
T = TypeVar('T')


class CreateConversationRequest(ApiModel):
    item_id: UUID


class SendMessageRequest(ApiModel):
    content: Content


class TimedResponse(ApiModel):
    @field_serializer('created_at', 'updated_at', check_fields=False)
    def serialize_time(self, value: datetime):
        return value.astimezone(ZoneInfo('Asia/Seoul')).isoformat()


class ConversationResponse(TimedResponse):
    conversation_id: UUID
    item_id: UUID
    finder_id: UUID
    member_id: UUID
    created_at: datetime
    updated_at: datetime


class MessageResponse(TimedResponse):
    message_id: UUID
    conversation_id: UUID
    sender_id: UUID
    content: str
    created_at: datetime


class MessagePage(ApiModel, Generic[T]):
    model_config = ConfigDict(populate_by_name=True)

    items: list[T]
    page: int
    size: int
    total_elements: int
    total_pages: int
