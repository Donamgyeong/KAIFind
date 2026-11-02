"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["profile"])


@router.get('/me/profile', summary='get profile', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def get_profile():
    """PROFILE-01: get profile. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "PROFILE-01 구현 예정"},
    )


@router.patch('/me/profile', summary='update profile', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def update_profile():
    """PROFILE-02: update profile. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "PROFILE-02 구현 예정"},
    )
