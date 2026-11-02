"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["notifications"])


@router.get('/me/notification-settings', summary='get notification settings', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def get_notification_settings():
    """NOTI-01: get notification settings. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "NOTI-01 구현 예정"},
    )


@router.put('/me/notification-settings', summary='update notification settings', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def update_notification_settings():
    """NOTI-02: update notification settings. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "NOTI-02 구현 예정"},
    )


@router.get('/me/notifications', summary='list notifications', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_notifications():
    """NOTI-03: list notifications. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "NOTI-03 구현 예정"},
    )


@router.patch('/me/notifications/{notificationId}', summary='mark notification read', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def mark_notification_read(notificationId: UUID):
    """NOTI-04: mark notification read. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "NOTI-04 구현 예정"},
    )
