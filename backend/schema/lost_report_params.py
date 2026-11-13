"""Lost report list filters."""

from pydantic import Field

from schema.common import ApiModel
from schema.lost_reports import LostReportStatus


class LostReportParams(ApiModel):
    page: int = Field(default=0, ge=0)
    size: int = Field(default=20, ge=1, le=100)
    status: LostReportStatus | None = None
