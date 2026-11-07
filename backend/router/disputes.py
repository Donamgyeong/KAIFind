"""Authenticated collection dispute submission and history."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from library.protected_http import ProtectedRoute
from schema.common import ErrorResponse
from schema.dispute_params import DisputeParams
from schema.disputes import CreateDisputeRequest, DisputePage, DisputeResponse
from service.disputes import DisputeService


router = APIRouter(
    tags=['disputes'], route_class=ProtectedRoute,
    responses={code: {'model': ErrorResponse} for code in (400, 401, 403, 404, 409, 415, 500)},
)


@router.post(
    '/found-items/{itemId}/disputes', summary='수거 이의 제기',
    status_code=201, response_model=DisputeResponse,
)
async def create_dispute(request: Request, itemId: UUID, body: CreateDisputeRequest):
    return await DisputeService(request).create(itemId, body.reason)


@router.get(
    '/found-items/{itemId}/disputes', summary='내 게시물 분쟁 목록',
    response_model=DisputePage,
)
async def list_item_disputes(
    request: Request, itemId: UUID, params: Annotated[DisputeParams, Query()],
):
    return await DisputeService(request).list(itemId, params)
