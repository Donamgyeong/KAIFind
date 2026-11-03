"""Admin API contracts. Explicit nulls are rejected on request fields."""
from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import (AfterValidator, AwareDatetime, ConfigDict, Field, StrictBool, StrictStr,
                      field_serializer, model_validator)
from schema.common import Affiliation, ApiModel, Role


def trimmed(value):
    value = value.strip()
    if not value:
        raise ValueError('must not be blank')
    return value

Name = Annotated[StrictStr, AfterValidator(trimmed), Field(min_length=1, max_length=100)]
Code = Annotated[StrictStr, AfterValidator(trimmed), Field(min_length=1, max_length=30)]
Details = Annotated[StrictStr, AfterValidator(trimmed), Field(min_length=1, max_length=1000)]
T = TypeVar('T')


class ResponseModel(ApiModel):
    model_config = ConfigDict(populate_by_name=True)
    @field_serializer('*', check_fields=False)
    def serialize_time(self, value):
        if isinstance(value, datetime):
            return value.astimezone(ZoneInfo('Asia/Seoul')).isoformat()
        return value


class Page(ResponseModel, Generic[T]):
    items: list[T]
    page: int
    size: int
    total_elements: int
    total_pages: int


class UpdateRoleRequest(ApiModel):
    role: Role


class CreateBuildingRequest(ApiModel):
    code: Code
    name_ko: Name
    name_en: Name


class PatchRequest(ApiModel):
    @model_validator(mode='after')
    def check_patch(self):
        if not self.model_fields_set:
            raise ValueError('at least one field required')
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('null is not allowed')
        return self


class UpdateBuildingRequest(PatchRequest):
    name_ko: Name | None = None
    name_en: Name | None = None
    active: StrictBool | None = None


class CreateCategoryRequest(ApiModel):
    name_ko: Name
    name_en: Name
    sensitive: StrictBool


class UpdateCategoryRequest(UpdateBuildingRequest):
    pass


class CreatePostReportRequest(ApiModel):
    reason_code: Literal['INAPPROPRIATE', 'SPAM', 'OTHER']
    details: Details


class ReviewPostReportRequest(ApiModel):
    decision: Literal['HIDE', 'DISMISS']


class ReviewDisputeRequest(ApiModel):
    decision: Literal['UPHELD', 'DISMISSED']
    block_collector: StrictBool


class UpdateCollectionRestrictionRequest(ApiModel):
    restricted: StrictBool
    dispute_id: UUID | None = None

    @model_validator(mode='after')
    def check_dispute(self):
        if 'dispute_id' in self.model_fields_set and self.dispute_id is None:
            raise ValueError('null is not allowed')
        if self.restricted and self.dispute_id is None:
            raise ValueError('disputeId is required when restricted')
        return self


class AdminUserSummary(ResponseModel):
    user_id: UUID
    name: str
    affiliation: Affiliation
    role: Role
    collection_restricted: bool


class BuildingResponse(ResponseModel):
    building_id: UUID
    code: str
    name_ko: str
    name_en: str
    active: bool


class CategoryResponse(ResponseModel):
    category_id: UUID
    name_ko: str
    name_en: str
    active: bool
    sensitive: bool


class PostReportResponse(ResponseModel):
    report_id: UUID
    item_id: UUID
    reporter_id: UUID
    reason_code: Literal['INAPPROPRIATE', 'SPAM', 'OTHER']
    details: str
    status: Literal['OPEN', 'REVIEWED']
    decision: Literal['HIDE', 'DISMISS'] | None
    created_at: AwareDatetime
    reviewed_at: AwareDatetime | None
    reviewer_id: UUID | None


class AdminDisputeResponse(ResponseModel):
    dispute_id: UUID
    item_id: UUID
    collection_id: UUID
    finder_id: UUID
    collector_id: UUID
    reason: str
    status: Literal['OPEN', 'RESOLVED']
    decision: Literal['UPHELD', 'DISMISSED'] | None
    created_at: AwareDatetime
    resolved_at: AwareDatetime | None


class CollectionRestrictionResponse(ResponseModel):
    user_id: UUID
    restricted: bool
    dispute_id: UUID | None
    updated_at: AwareDatetime


class StatisticsResponse(ResponseModel):
    posted_count: int
    collected_count: int
    expired_count: int
    as_of: AwareDatetime


AuditAction = Literal['ITEM_STATUS_CHANGED', 'COLLECTION_MARKED', 'COLLECTION_UNDONE',
    'DROP_OFF_CHANGED', 'SENSITIVE_PHOTO_VIEWED', 'SENSITIVE_DROP_OFF_VIEWED',
    'LOST_REPORT_STATUS_CHANGED', 'PHOTO_ACCESS_URL_ISSUED', 'ROLE_CHANGED',
    'REFERENCE_CREATED', 'REFERENCE_UPDATED', 'POST_HIDDEN', 'POST_REPORT_REVIEWED',
    'DISPUTE_REVIEWED', 'COLLECTION_RESTRICTION_CHANGED']


class AuditLogResponse(ResponseModel):
    audit_log_id: UUID
    actor_id: UUID | None
    actor_type: Literal['MEMBER', 'ADMIN', 'SYSTEM']
    action: AuditAction
    target_type: Literal['FOUND_ITEM', 'LOST_REPORT', 'COLLECTION', 'USER', 'BUILDING', 'CATEGORY', 'POST_REPORT', 'DISPUTE']
    target_id: UUID
    occurred_at: AwareDatetime
    metadata: dict
