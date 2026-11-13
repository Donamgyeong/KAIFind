"""Found item registration and public response contracts."""

from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime, Field, StrictStr, StringConstraints, field_serializer, field_validator,
    model_validator,
)

from schema.common import ApiModel
from schema.matching import TextAnalysisProgress
from schema.reference import CategorySummary


Title = Annotated[StrictStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[StrictStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
LocationText = Annotated[StrictStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
AltText = Annotated[StrictStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class PhotoAttachmentInput(ApiModel):
    photo_id: UUID
    alt_text: AltText


class DropOffLocation(ApiModel):
    mode: Literal['DROP_OFF']
    building_id: UUID
    spot_description: LocationText
    photo: PhotoAttachmentInput | None = None


class KeptByFinder(ApiModel):
    mode: Literal['KEPT_BY_FINDER']


DropOffInput = Annotated[DropOffLocation | KeptByFinder, Field(discriminator='mode')]


class CreateFoundItemRequest(ApiModel):
    category_id: UUID
    title: Title
    description: Description
    found_building_id: UUID
    found_location_description: LocationText
    found_at: AwareDatetime
    photos: list[PhotoAttachmentInput] = Field(min_length=1, max_length=5)
    drop_off: DropOffInput

    @field_validator('found_at', mode='before')
    @classmethod
    def timestamp_string(cls, value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('Expected RFC3339 timestamp with timezone')
        return value

    @model_validator(mode='after')
    def unique_photos(self):
        ids = [photo.photo_id for photo in self.photos]
        if isinstance(self.drop_off, DropOffLocation) and self.drop_off.photo:
            ids.append(self.drop_off.photo.photo_id)
        if len(set(ids)) != len(ids):
            raise ValueError('Photo IDs must be unique across item and storage photos')
        return self


class BuildingSummary(ApiModel):
    building_id: UUID
    code: str
    name_ko: str
    name_en: str
    active: bool


class PhotoMetadata(ApiModel):
    photo_id: UUID
    alt_text: str
    access_requires_login: bool


class FinderSummary(ApiModel):
    user_id: UUID


class FoundItemSummary(ApiModel):
    item_id: UUID
    category: CategorySummary
    title: str
    status: Literal['POSTED', 'COLLECTED', 'EXPIRED']
    found_building: BuildingSummary
    found_at: AwareDatetime
    created_at: AwareDatetime
    photos: list[PhotoMetadata]
    sensitive: bool
    hidden: bool

    @field_serializer('found_at', 'created_at')
    def serialize_time(self, value):
        return value.astimezone(ZoneInfo('Asia/Seoul')).isoformat()


class FoundItemDetail(FoundItemSummary, TextAnalysisProgress):
    description: str
    found_location_description: str
    finder: FinderSummary
    updated_at: AwareDatetime
    posted_at: AwareDatetime
    expires_at: AwareDatetime
    closed_at: AwareDatetime | None

    @field_serializer('updated_at', 'posted_at', 'expires_at', 'closed_at')
    def serialize_detail_time(self, value):
        return value.astimezone(ZoneInfo('Asia/Seoul')).isoformat() if value else None
