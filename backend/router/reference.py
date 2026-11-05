"""Public active buildings and categories."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from library.reference_http import ReferenceRoute
from router.reference_params import BuildingParams, CategoryParams
from schema.common import ErrorResponse
from schema.reference import BuildingListResponse, CategoryListResponse
from service.reference import ReferenceService


router = APIRouter(
    tags=['reference'],
    route_class=ReferenceRoute,
    responses={code: {'model': ErrorResponse} for code in (400, 500)},
)


@router.get(
    '/buildings', summary='활성 건물 목록·집계',
    response_model=BuildingListResponse, response_model_exclude_none=True,
)
async def list_buildings(request: Request, params: Annotated[BuildingParams, Query()]):
    return await ReferenceService(request.state.db).buildings(params.include_posted_count)


@router.get(
    '/categories', summary='활성 카테고리', response_model=CategoryListResponse,
)
async def list_categories(request: Request, params: Annotated[CategoryParams, Query()]):
    return await ReferenceService(request.state.db).categories()
