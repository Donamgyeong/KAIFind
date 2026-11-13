"""Authenticated lost report lifecycle endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from library.auth_http import error_response
from library.protected_http import ProtectedRoute
from schema.common import ErrorResponse
from schema.lost_report_params import LostReportParams
from schema.lost_reports import (
    CreateLostReportRequest, LostReportPage, LostReportResponse, UpdateLostReportRequest,
)
from service.auth import AuthError
from service.lost_reports import LostReportService


router = APIRouter(
    tags=['lost_reports'], route_class=ProtectedRoute,
    responses={'default': {'model': ErrorResponse, 'description': '공통 오류'}},
)


def mutation_response(result, request):
    # Return the error normally so an expiry transition commits with the response.
    if result is None:
        return error_response(AuthError(409, 'LOST_REPORT_NOT_OPEN'), request)
    return result


@router.post('/lost-reports', response_model=LostReportResponse, status_code=201)
async def create_lost_report(request: Request, body: CreateLostReportRequest, response: Response):
    result = await LostReportService(request).create(body)
    response.headers['Location'] = f'/api/v1/lost-reports/{result.report_id}'
    return result


@router.get('/lost-reports', response_model=LostReportPage)
async def list_lost_reports(request: Request, params: Annotated[LostReportParams, Query()]):
    return await LostReportService(request).list(params)


@router.get('/lost-reports/{reportId}', response_model=LostReportResponse)
async def get_lost_report(request: Request, reportId: UUID):
    service = LostReportService(request)
    return await service.response(await service.load(reportId))


@router.put('/lost-reports/{reportId}', response_model=LostReportResponse)
async def update_lost_report(request: Request, reportId: UUID, body: UpdateLostReportRequest):
    return mutation_response(await LostReportService(request).update(reportId, body), request)


@router.post('/lost-reports/{reportId}/extend', response_model=LostReportResponse)
async def extend_lost_report(request: Request, reportId: UUID):
    return mutation_response(await LostReportService(request).extend(reportId), request)


@router.post('/lost-reports/{reportId}/resolve', response_model=LostReportResponse)
async def resolve_lost_report(request: Request, reportId: UUID):
    return await LostReportService(request).resolve(reportId)
