"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["disputes"])


@router.post('/found-items/{itemId}/disputes', summary='수거 이의 제기', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def create_dispute(itemId: UUID):
    """DSP-01: 수거 이의 제기. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "DSP-01 구현 예정"},
    )


@router.get('/found-items/{itemId}/disputes', summary='내 게시물 분쟁 목록', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_item_disputes(itemId: UUID):
    """DSP-02: 내 게시물 분쟁 목록. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "DSP-02 구현 예정"},
    )
