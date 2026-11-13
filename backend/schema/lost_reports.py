"""Owner-scoped lost report contracts."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime, Field, StrictStr, StringConstraints, field_serializer, field_validator,
    model_validator,
)

from schema.common import ApiModel
from schema.matching import MatchingProgress


LostReportStatus = Literal['OPEN', 'RESOLVED', 'CLOSED']


class CreateLostReportRequest(ApiModel):
    category_id: UUID
    description: Annotated[StrictStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    possible_building_ids: list[UUID] = Field(min_length=1, max_length=100)
    lost_date_from: date
    lost_date_to: date
    private_identifying_details: Annotated[
        StrictStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
    ]

    @field_validator('lost_date_from', 'lost_date_to', mode='before')
    @classmethod
    def date_strings(cls, value):
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError('Expected YYYY-MM-DD')
        return value

    @model_validator(mode='after')
    def validate_range_and_buildings(self):
        if self.lost_date_from > self.lost_date_to:
            raise ValueError('lostDateFrom must not exceed lostDateTo')
        if len(set(self.possible_building_ids)) != len(self.possible_building_ids):
            raise ValueError('possibleBuildingIds must be unique')
        return self


class UpdateLostReportRequest(CreateLostReportRequest):
    pass


class LostReportSummary(MatchingProgress):
    report_id: UUID
    owner_id: UUID
    category_id: UUID
    description: str
    possible_building_ids: list[UUID]
    lost_date_from: date
    lost_date_to: date
    status: LostReportStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime
    expires_at: AwareDatetime
    closed_at: AwareDatetime | None

    @field_serializer('created_at', 'updated_at', 'expires_at', 'closed_at')
    def serialize_time(self, value):
        return value.astimezone(ZoneInfo('Asia/Seoul')).isoformat() if value else None


class LostReportResponse(LostReportSummary):
    private_identifying_details: str | None


class LostReportPage(ApiModel):
    items: list[LostReportSummary]
    page: int
    size: int
    total_elements: int
    total_pages: int
