"""Private notification request and response contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import StrictBool, field_serializer, field_validator

from schema.common import ApiModel


class UpdateNotificationSettingsRequest(ApiModel):
    email_enabled: StrictBool
    match_email: StrictBool
    collection_email: StrictBool
    expiry_email: StrictBool
    keyword_email: StrictBool


class NotificationSettingsResponse(UpdateNotificationSettingsRequest):
    pass


class UpdateNotificationRequest(ApiModel):
    read: StrictBool

    @field_validator('read')
    @classmethod
    def require_read(cls, value):
        if not value:
            raise ValueError('Only read=true is allowed')
        return value


class NotificationResponse(ApiModel):
    notification_id: UUID
    type: Literal['MATCH_CANDIDATE', 'ITEM_COLLECTED', 'ITEM_EXPIRED', 'KEYWORD_MATCH']
    message: str
    target_path: str
    item_id: UUID | None
    report_id: UUID | None
    created_at: datetime
    read_at: datetime | None

    @field_serializer('created_at', 'read_at')
    def serialize_time(self, value):
        return value.astimezone(ZoneInfo('Asia/Seoul')).isoformat() if value else None


class NotificationPage(ApiModel):
    items: list[NotificationResponse]
    page: int
    size: int
    total_elements: int
    total_pages: int
