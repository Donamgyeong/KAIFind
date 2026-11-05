"""Public reference query contracts."""

from schema.common import ApiModel


class BuildingParams(ApiModel):
    include_posted_count: bool = False


class CategoryParams(ApiModel):
    """Categories accept no query fields."""
