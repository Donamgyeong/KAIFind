"""Authenticated, read-only matching candidates."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from library.protected_http import ProtectedRoute
from schema.common import ErrorResponse
from schema.matching import MatchCandidatePage
from schema.matching_params import MatchingParams
from service.matching import read_matches


router = APIRouter(
    tags=['matching'], route_class=ProtectedRoute,
    responses={code: {'model': ErrorResponse} for code in (400, 401, 404, 500)},
)


@router.get(
    '/lost-reports/{reportId}/matches', summary='내 신고의 매칭 후보 조회',
    response_model=MatchCandidatePage,
)
async def list_matches(request: Request, reportId: UUID, params: Annotated[MatchingParams, Query()]):
    return await read_matches(
        request.state.db, report_id=reportId, now=request.state.now,
        user_id=request.state.user.id, admin=request.state.user.role == 'ADMIN',
        page=params.page, size=params.size,
    )
