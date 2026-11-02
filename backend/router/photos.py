"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["photos"])


@router.post('/photos', summary='사진 업로드', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def upload_photo():
    """PHOTO-01: 사진 업로드. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "PHOTO-01 구현 예정"},
    )


@router.post('/photos/{photoId}/access-url', summary='사진 단기 링크', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def create_photo_access_url(photoId: UUID):
    """PHOTO-02: 사진 단기 링크. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "PHOTO-02 구현 예정"},
    )


@router.get('/photo-access/{accessToken}', summary='사진 바이트', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def get_photo_content(accessToken: str):
    """PHOTO-03: 사진 바이트. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "PHOTO-03 구현 예정"},
    )
