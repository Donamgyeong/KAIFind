"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from library.optional_http import OptionalAuthRoute
from library.protected_http import ProtectedRoute
from schema.admin import CreatePostReportRequest, PostReportResponse
from schema.common import ErrorResponse
from schema.found_item_params import FoundItemListParams, MyFoundItemParams, PageParams
from schema.found_items import (
    CreateFoundItemRequest, DropOffHistoryPage, DropOffInput, DropOffResponse, FoundItemDetail,
    FoundItemPage, UpdateFoundItemRequest,
)
from service.admin import AdminService
from service.found_items import FoundItemService


class FoundItemWriteRoute(ProtectedRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            response = await handler(request)
            response.headers['Cache-Control'] = 'private, no-store'
            return response

        return handle


router = APIRouter(tags=["found_items"])


def errors(*codes):
    return {code: {'model': ErrorResponse} for code in codes}


# Public reads: guests allowed; a live session widens what the caller may see.
async def list_found_items(request: Request, params: Annotated[FoundItemListParams, Query()]):
    return await FoundItemService(request).search(params)


router.add_api_route(
    '/found-items', list_found_items, methods=['GET'], summary='검색·목록',
    response_model=FoundItemPage, route_class_override=OptionalAuthRoute,
    responses=errors(400, 500),
)


async def get_found_item(request: Request, itemId: UUID):
    return await FoundItemService(request).get(itemId)


router.add_api_route(
    '/found-items/{itemId}', get_found_item, methods=['GET'], summary='공개 상세',
    response_model=FoundItemDetail, route_class_override=OptionalAuthRoute,
    responses=errors(400, 404, 500),
)


async def create_found_item(request: Request, body: CreateFoundItemRequest, response: Response):
    result = await FoundItemService(request).create(body)
    response.headers['Location'] = f'/api/v1/found-items/{result.item_id}'
    return result


router.add_api_route(
    '/found-items', create_found_item, methods=['POST'], summary='습득물 등록',
    status_code=201, response_model=FoundItemDetail, route_class_override=FoundItemWriteRoute,
    responses={code: {'model': ErrorResponse} for code in (400, 401, 403, 409, 415, 500)},
)


# Finder-only writes and member-only reads share the protected transaction.
async def update_found_item(request: Request, itemId: UUID, body: UpdateFoundItemRequest):
    return await FoundItemService(request).update(itemId, body)


router.add_api_route(
    '/found-items/{itemId}', update_found_item, methods=['PATCH'], summary='자기 게시물 수정',
    response_model=FoundItemDetail, route_class_override=FoundItemWriteRoute,
    responses=errors(400, 401, 403, 404, 409, 415, 500),
)


async def delete_found_item(request: Request, itemId: UUID):
    await FoundItemService(request).delete(itemId)
    return Response(status_code=204)


router.add_api_route(
    '/found-items/{itemId}', delete_found_item, methods=['DELETE'], summary='자기 게시물 삭제',
    status_code=204, route_class_override=FoundItemWriteRoute,
    responses=errors(400, 401, 403, 404, 500),
)


async def get_drop_off(request: Request, itemId: UUID):
    return await FoundItemService(request).drop_off(itemId)


router.add_api_route(
    '/found-items/{itemId}/drop-off', get_drop_off, methods=['GET'], summary='보관 위치 조회',
    response_model=DropOffResponse, route_class_override=FoundItemWriteRoute,
    responses=errors(400, 401, 404, 500),
)


async def update_drop_off(request: Request, itemId: UUID, body: DropOffInput):
    return await FoundItemService(request).change_drop_off(itemId, body)


router.add_api_route(
    '/found-items/{itemId}/drop-off', update_drop_off, methods=['PUT'], summary='보관 위치 변경',
    response_model=DropOffResponse, route_class_override=FoundItemWriteRoute,
    responses=errors(400, 401, 403, 404, 409, 415, 500),
)


async def list_drop_off_history(
    request: Request, itemId: UUID, params: Annotated[PageParams, Query()],
):
    return await FoundItemService(request).drop_off_history(itemId, params)


router.add_api_route(
    '/found-items/{itemId}/drop-off/history', list_drop_off_history, methods=['GET'],
    summary='보관 위치 이력', response_model=DropOffHistoryPage,
    route_class_override=FoundItemWriteRoute, responses=errors(400, 401, 404, 500),
)


async def repost_found_item(request: Request, itemId: UUID):
    return await FoundItemService(request).repost(itemId)


router.add_api_route(
    '/found-items/{itemId}/repost', repost_found_item, methods=['POST'], summary='만료 재등록',
    response_model=FoundItemDetail, route_class_override=FoundItemWriteRoute,
    responses=errors(400, 401, 403, 404, 409, 500),
)


async def list_my_found_items(request: Request, params: Annotated[MyFoundItemParams, Query()]):
    return await FoundItemService(request).list_mine(params)


# Login is required, so this shares the protected transaction and private cache header.
router.add_api_route(
    '/me/found-items', list_my_found_items, methods=['GET'], summary='내 게시물',
    response_model=FoundItemPage, route_class_override=FoundItemWriteRoute,
    responses={code: {'model': ErrorResponse} for code in (400, 401, 500)},
)


# MOD-01 shares the protected transaction wrapper with admin review endpoints.


async def report_found_item(request: Request, itemId: UUID, body: CreatePostReportRequest):
    return await AdminService(request).create_report(itemId, body)


router.add_api_route('/found-items/{itemId}/reports', report_found_item, methods=['POST'],
    summary='부적절한 게시물 신고', status_code=201, response_model=PostReportResponse,
    route_class_override=ProtectedRoute,
    responses={code: {'model': ErrorResponse} for code in (400, 401, 403, 404, 409, 415, 500)})
