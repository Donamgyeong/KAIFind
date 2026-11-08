"""Shared progress and candidate response contracts for asynchronous matching."""
from enum import StrEnum
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, StrictBool, field_serializer, model_validator

from schema.common import ApiModel


class ProcessingStatus(StrEnum):
    PENDING = 'PENDING'
    PROCESSING = 'PROCESSING'
    READY = 'READY'
    FAILED = 'FAILED'


class TextAnalysisProgress(ApiModel):
    analysis_status: ProcessingStatus


class MatchingProgress(TextAnalysisProgress):
    matching_status: ProcessingStatus


class MatchItemSummary(ApiModel):
    item_id: UUID
    category_id: UUID
    found_building_id: UUID
    title: str
    found_at: AwareDatetime
    status: Literal['POSTED', 'COLLECTED', 'EXPIRED']
    sensitive: StrictBool

    @field_serializer('found_at')
    def serialize_time(self, value):
        return value.astimezone(ZoneInfo('Asia/Seoul')).isoformat()


class MatchCandidateResponse(ApiModel):
    candidate_id: UUID
    report_id: UUID
    item_id: UUID
    matched_at: AwareDatetime
    matched_by: list[Literal['BUILDING', 'KEYWORD']] = Field(min_length=1, max_length=2)
    item: MatchItemSummary

    @model_validator(mode='after')
    def unique_reasons(self):
        if len(set(self.matched_by)) != len(self.matched_by):
            raise ValueError('matchedBy must not contain duplicate reasons')
        return self

    @field_serializer('matched_at')
    def serialize_time(self, value):
        return value.astimezone(ZoneInfo('Asia/Seoul')).isoformat()


class MatchCandidatePage(MatchingProgress):
    items: list[MatchCandidateResponse]
    page: int = Field(ge=0)
    size: int = Field(ge=1, le=100)
    total_elements: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    is_complete: StrictBool

    @model_validator(mode='after')
    def consistent_completion(self):
        if self.is_complete != (self.matching_status == ProcessingStatus.READY):
            raise ValueError('isComplete must agree with matchingStatus')
        return self
