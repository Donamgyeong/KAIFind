"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["reference"])


@router.get('/buildings', summary='활성 건물 목록·집계', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_buildings():
    """REF-01: 활성 건물 목록·집계. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "REF-01 구현 예정"},
    )


@router.get('/categories', summary='활성 카테고리', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_categories():
    """REF-02: 활성 카테고리. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "REF-02 구현 예정"},
    )
