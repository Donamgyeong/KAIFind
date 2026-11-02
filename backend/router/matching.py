"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["matching"])


@router.get('/lost-reports/{reportId}/matches', summary='list matches', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_matches(reportId: UUID):
    """MATCH-01: list matches. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "MATCH-01 구현 예정"},
    )
