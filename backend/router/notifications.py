"""Private notification settings, list and read endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from library.protected_http import ProtectedRoute
from schema.common import ErrorResponse
from schema.notification_params import NotificationParams
from schema.notifications import (
    NotificationPage, NotificationResponse, NotificationSettingsResponse,
    UpdateNotificationRequest, UpdateNotificationSettingsRequest,
)
from service.notifications import NotificationService


router = APIRouter(
    tags=['notifications'], route_class=ProtectedRoute,
    responses={code: {'model': ErrorResponse} for code in (400, 401, 403, 415, 500)},
)


@router.get('/me/notification-settings', response_model=NotificationSettingsResponse,
            summary='이메일 알림 설정 조회')
async def get_notification_settings(request: Request):
    return await NotificationService(request).settings()


@router.put('/me/notification-settings', response_model=NotificationSettingsResponse,
            summary='이메일 알림 설정 변경')
async def update_notification_settings(request: Request, body: UpdateNotificationSettingsRequest):
    return await NotificationService(request).replace_settings(body)


@router.get('/me/notifications', response_model=NotificationPage, summary='내 알림 목록')
async def list_notifications(request: Request, params: Annotated[NotificationParams, Query()]):
    return await NotificationService(request).list(params)


@router.patch('/me/notifications/{notificationId}', response_model=NotificationResponse,
              summary='알림 확인 처리', responses={404: {'model': ErrorResponse}})
async def mark_notification_read(
    request: Request, notificationId: UUID, body: UpdateNotificationRequest,
):
    return await NotificationService(request).mark_read(notificationId)
