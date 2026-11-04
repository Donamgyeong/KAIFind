"""Photo contracts; original filenames and storage keys are never exposed."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from schema.common import ApiModel


class PhotoPurpose(StrEnum):
    ITEM = 'ITEM'
    DROP_OFF = 'DROP_OFF'


class PhotoUploadResponse(ApiModel):
    photo_id: UUID
    purpose: PhotoPurpose
    content_type: str
    size_bytes: int
    width: int
    height: int
    unattached_expires_at: datetime


class PhotoAccessResponse(ApiModel):
    url: str
    expires_at: datetime
    content_type: str
