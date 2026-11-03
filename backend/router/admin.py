"""Admin endpoints; authorization and transaction handling are shared by ProtectedRoute."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from library.protected_http import ProtectedRoute
from model import Building, Category
from router.admin_params import AuditParams, DisputesParams, ReferenceParams, ReportsParams, UsersParams
from schema.admin import (AdminDisputeResponse, AdminUserSummary, AuditLogResponse,
    BuildingResponse, CategoryResponse, CollectionRestrictionResponse,
    CreateBuildingRequest, CreateCategoryRequest, Page, PostReportResponse,
    ReviewDisputeRequest, ReviewPostReportRequest, StatisticsResponse,
    UpdateBuildingRequest, UpdateCategoryRequest, UpdateCollectionRestrictionRequest, UpdateRoleRequest)
from schema.common import ErrorResponse
from service.admin import AdminService

router = APIRouter(tags=['admin'], route_class=ProtectedRoute,
    responses={code: {'model': ErrorResponse} for code in (400, 401, 403, 404, 409, 415, 500)})


@router.get('/admin/users', response_model=Page[AdminUserSummary], summary='권한 관리용 회원 조회')
async def list_users(request: Request, params: Annotated[UsersParams, Query()]):
    return await AdminService(request).users(params)


@router.patch('/admin/users/{userId}/role', response_model=AdminUserSummary, summary='관리자 권한 부여·회수')
async def update_user_role(request: Request, userId: UUID, body: UpdateRoleRequest):
    return await AdminService(request).role(userId, body)


@router.get('/admin/buildings', response_model=Page[BuildingResponse], summary='건물 전체 목록')
async def list_buildings(request: Request, params: Annotated[ReferenceParams, Query()]):
    return await AdminService(request).references(Building, params)


@router.post('/admin/buildings', response_model=BuildingResponse, status_code=201, summary='건물 추가')
async def create_building(request: Request, body: CreateBuildingRequest):
    return await AdminService(request).create_reference(Building, body)


@router.patch('/admin/buildings/{buildingId}', response_model=BuildingResponse, summary='건물 이름 변경·비활성화')
async def update_building(request: Request, buildingId: UUID, body: UpdateBuildingRequest):
    return await AdminService(request).update_reference(Building, buildingId, body)


@router.get('/admin/categories', response_model=Page[CategoryResponse], summary='카테고리 전체 목록')
async def list_categories(request: Request, params: Annotated[ReferenceParams, Query()]):
    return await AdminService(request).references(Category, params)


@router.post('/admin/categories', response_model=CategoryResponse, status_code=201, summary='카테고리 추가')
async def create_category(request: Request, body: CreateCategoryRequest):
    return await AdminService(request).create_reference(Category, body)


@router.patch('/admin/categories/{categoryId}', response_model=CategoryResponse, summary='카테고리 이름 변경·비활성화')
async def update_category(request: Request, categoryId: UUID, body: UpdateCategoryRequest):
    return await AdminService(request).update_reference(Category, categoryId, body)


@router.get('/admin/post-reports', response_model=Page[PostReportResponse], summary='게시물 신고 목록')
async def list_post_reports(request: Request, params: Annotated[ReportsParams, Query()]):
    return await AdminService(request).reports(params)


@router.get('/admin/post-reports/{reportId}', response_model=PostReportResponse, summary='게시물 신고 상세')
async def get_post_report(request: Request, reportId: UUID):
    return await AdminService(request).report(reportId)


@router.post('/admin/post-reports/{reportId}/review', response_model=PostReportResponse, summary='신고 검토·숨김')
async def review_post_report(request: Request, reportId: UUID, body: ReviewPostReportRequest):
    return await AdminService(request).review_report(reportId, body)


@router.get('/admin/disputes', response_model=Page[AdminDisputeResponse], summary='수거 분쟁 목록')
async def list_disputes(request: Request, params: Annotated[DisputesParams, Query()]):
    return await AdminService(request).disputes(params)


@router.get('/admin/disputes/{disputeId}', response_model=AdminDisputeResponse, summary='수거 분쟁 상세')
async def get_dispute(request: Request, disputeId: UUID):
    return await AdminService(request).dispute(disputeId)


@router.post('/admin/disputes/{disputeId}/review', response_model=AdminDisputeResponse, summary='수거 분쟁 검토')
async def review_dispute(request: Request, disputeId: UUID, body: ReviewDisputeRequest):
    return await AdminService(request).review_dispute(disputeId, body)


@router.put('/admin/users/{userId}/collection-restriction', response_model=CollectionRestrictionResponse, summary='수거 권한 제한·해제')
async def update_collection_restriction(request: Request, userId: UUID, body: UpdateCollectionRestrictionRequest):
    return await AdminService(request).restriction(userId, body.restricted, body.dispute_id)


@router.get('/admin/statistics', response_model=StatisticsResponse, summary='상태별 기본 통계')
async def get_statistics(request: Request):
    return await AdminService(request).statistics()


@router.get('/admin/audit-logs', response_model=Page[AuditLogResponse], summary='감사 로그 조회')
async def list_audit_logs(request: Request, params: Annotated[AuditParams, Query()]):
    return await AdminService(request).audits(params)
