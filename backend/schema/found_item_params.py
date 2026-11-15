"""Found item list query contracts."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from schema.common import ApiModel


ItemStatus = Literal['POSTED', 'COLLECTED', 'EXPIRED']


class PageParams(ApiModel):
    page: int = Field(default=0, ge=0)
    size: int = Field(default=20, ge=1, le=100)


class MyFoundItemParams(PageParams):
    statuses: list[ItemStatus] | None = None


class FoundItemListParams(MyFoundItemParams):
    q: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None
    category_id: UUID | None = None
    found_building_id: UUID | None = None
    found_date_from: date | None = None
    found_date_to: date | None = None

    @field_validator('found_date_from', 'found_date_to', mode='before')
    @classmethod
    def date_strings(cls, value):
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError('Expected YYYY-MM-DD')
        return value

    @model_validator(mode='after')
    def validate_range(self):
        if self.found_date_from and self.found_date_to and self.found_date_from > self.found_date_to:
            raise ValueError('foundDateFrom must not exceed foundDateTo')
        return self
