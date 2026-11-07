"""Query contracts for conversation and message lists."""

from uuid import UUID

from pydantic import Field

from schema.common import ApiModel


class MessageParams(ApiModel):
    page: int = Field(default=0, ge=0)
    size: int = Field(default=20, ge=1, le=100)


class ConversationParams(MessageParams):
    item_id: UUID | None = None
