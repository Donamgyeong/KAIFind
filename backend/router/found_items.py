"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status

from library.protected_http import ProtectedRoute
from schema.admin import CreatePostReportRequest, PostReportResponse
from schema.common import ErrorResponse
from schema.found_items import CreateFoundItemRequest, FoundItemDetail
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


@router.get('/found-items', summary='검색·목록', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_found_items():
    """ITEM-01: 검색·목록. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ITEM-01 구현 예정"},
    )


@router.get('/found-items/{itemId}', summary='공개 상세', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def get_found_item(itemId: UUID):
    """ITEM-02: 공개 상세. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ITEM-02 구현 예정"},
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


@router.patch('/found-items/{itemId}', summary='자기 게시물 수정', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def update_found_item(itemId: UUID):
    """ITEM-04: 자기 게시물 수정. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ITEM-04 구현 예정"},
    )


@router.delete('/found-items/{itemId}', summary='자기 게시물 삭제', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def delete_found_item(itemId: UUID):
    """ITEM-05: 자기 게시물 삭제. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ITEM-05 구현 예정"},
    )


@router.get('/found-items/{itemId}/drop-off', summary='보관 위치 조회', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def get_drop_off(itemId: UUID):
    """ITEM-06: 보관 위치 조회. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ITEM-06 구현 예정"},
    )


@router.put('/found-items/{itemId}/drop-off', summary='보관 위치 변경', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def update_drop_off(itemId: UUID):
    """ITEM-07: 보관 위치 변경. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ITEM-07 구현 예정"},
    )


@router.get('/found-items/{itemId}/drop-off/history', summary='보관 위치 이력', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_drop_off_history(itemId: UUID):
    """ITEM-08: 보관 위치 이력. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ITEM-08 구현 예정"},
    )


@router.post('/found-items/{itemId}/repost', summary='만료 재등록', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def repost_found_item(itemId: UUID):
    """ITEM-09: 만료 재등록. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ITEM-09 구현 예정"},
    )


@router.get('/me/found-items', summary='내 게시물', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_my_found_items():
    """ITEM-10: 내 게시물. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ITEM-10 구현 예정"},
    )


# MOD-01 shares the protected transaction wrapper with admin review endpoints.


async def report_found_item(request: Request, itemId: UUID, body: CreatePostReportRequest):
    return await AdminService(request).create_report(itemId, body)


router.add_api_route('/found-items/{itemId}/reports', report_found_item, methods=['POST'],
    summary='부적절한 게시물 신고', status_code=201, response_model=PostReportResponse,
    route_class_override=ProtectedRoute,
    responses={code: {'model': ErrorResponse} for code in (400, 401, 403, 404, 409, 415, 500)})
