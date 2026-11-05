"""Public reference response contracts."""

from uuid import UUID

from pydantic import Field

from schema.common import ApiModel


class BuildingCountSummary(ApiModel):
    building_id: UUID
    code: str
    name_ko: str
    name_en: str
    active: bool
    posted_count: int | None = Field(default=None, ge=0)


class BuildingListResponse(ApiModel):
    items: list[BuildingCountSummary]


class CategorySummary(ApiModel):
    category_id: UUID
    name_ko: str
    name_en: str
    active: bool
    sensitive: bool


class CategoryListResponse(ApiModel):
    items: list[CategorySummary]
