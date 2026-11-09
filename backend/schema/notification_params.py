"""Notification list query contract."""

from pydantic import Field

from schema.common import ApiModel


class NotificationParams(ApiModel):
    page: int = Field(default=0, ge=0)
    size: int = Field(default=20, ge=1, le=100)
    unread_only: bool = False
