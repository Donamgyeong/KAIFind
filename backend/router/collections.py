"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["collections"])


@router.post('/found-items/{itemId}/collection', summary='수거 완료', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def mark_collection(itemId: UUID):
    """COL-01: 수거 완료. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "COL-01 구현 예정"},
    )


@router.get('/found-items/{itemId}/collection', summary='현재 수거 기록', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def get_collection(itemId: UUID):
    """COL-02: 현재 수거 기록. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "COL-02 구현 예정"},
    )


@router.delete('/found-items/{itemId}/collection', summary='잘못된 수거 취소', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def cancel_collection(itemId: UUID):
    """COL-03: 잘못된 수거 취소. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "COL-03 구현 예정"},
    )
