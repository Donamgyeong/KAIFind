"""Query DTOs used directly by FastAPI so aliases appear in OpenAPI."""
from uuid import UUID
from typing import Literal

from pydantic import AwareDatetime, Field
from schema.admin import AuditAction, Name
from schema.common import ApiModel, Role


class Pagination(ApiModel):
    page: int = Field(default=0, ge=0)
    size: int = Field(default=20, ge=1, le=100)


class UsersParams(Pagination):
    q: Name | None = None
    role: Role | None = None


class ReferenceParams(Pagination):
    active: bool | None = None


class ReportsParams(Pagination):
    status: Literal['OPEN', 'REVIEWED'] | None = None
    item_id: UUID | None = None


class DisputesParams(Pagination):
    status: Literal['OPEN', 'RESOLVED'] = 'OPEN'
    item_id: UUID | None = None


class AuditParams(Pagination):
    actor_id: UUID | None = None
    target_id: UUID | None = None
    action: AuditAction | None = None
    from_time: AwareDatetime | None = Field(default=None, alias='from')
    to_time: AwareDatetime | None = Field(default=None, alias='to')
