"""Query parameters for MATCH-01; HTTP extraction remains in the router."""
from pydantic import Field

from schema.common import ApiModel


class MatchingParams(ApiModel):
    page: int = Field(default=0, ge=0)
    size: int = Field(default=20, ge=1, le=100)
