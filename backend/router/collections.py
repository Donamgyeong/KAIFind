"""Authenticated collection lifecycle."""

from uuid import UUID

from fastapi import APIRouter, Request, Response

from library.protected_http import ProtectedRoute
from schema.collections import CollectRequest, CollectionResponse
from schema.common import ErrorResponse
from service.collections import CollectionService


router = APIRouter(
    tags=['collections'], route_class=ProtectedRoute,
    responses={code: {'model': ErrorResponse} for code in (400, 401, 403, 404, 409, 415, 500)},
)


@router.post(
    '/found-items/{itemId}/collection', summary='수거 완료',
    status_code=201, response_model=CollectionResponse,
)
async def mark_collection(request: Request, itemId: UUID, body: CollectRequest):
    return await CollectionService(request).collect(itemId)


@router.get(
    '/found-items/{itemId}/collection', summary='현재 수거 기록',
    response_model=CollectionResponse,
)
async def get_collection(request: Request, itemId: UUID):
    return await CollectionService(request).get(itemId)


@router.delete('/found-items/{itemId}/collection', summary='잘못된 수거 취소', status_code=204)
async def cancel_collection(request: Request, itemId: UUID):
    await CollectionService(request).cancel(itemId)
    return Response(status_code=204)
