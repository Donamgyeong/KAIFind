"""Private profile endpoints for the authenticated user."""

from fastapi import APIRouter, Request

from library.protected_http import ProtectedRoute
from schema.common import ErrorResponse
from schema.profile import ProfileResponse, UpdateProfileRequest
from service.profile import ProfileService


router = APIRouter(
    tags=['profile'],
    route_class=ProtectedRoute,
    responses={'default': {'model': ErrorResponse, 'description': '공통 오류'}},
)


@router.get(
    '/me/profile',
    summary='내 프로필 조회',
    response_model=ProfileResponse,
    responses={code: {'model': ErrorResponse} for code in (401, 500)},
)
async def get_profile(request: Request):
    return ProfileService(request).get()


@router.patch(
    '/me/profile',
    summary='내 언어 설정 변경',
    response_model=ProfileResponse,
    responses={code: {'model': ErrorResponse} for code in (400, 401, 403, 415, 500)},
)
async def update_profile(request: Request, body: UpdateProfileRequest):
    return await ProfileService(request).update(body)
