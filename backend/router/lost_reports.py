"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["lost_reports"])


@router.post('/lost-reports', summary='create lost report', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def create_lost_report():
    """LOST-01: create lost report. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "LOST-01 구현 예정"},
    )


@router.get('/lost-reports', summary='list lost reports', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_lost_reports():
    """LOST-02: list lost reports. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "LOST-02 구현 예정"},
    )


@router.get('/lost-reports/{reportId}', summary='get lost report', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def get_lost_report(reportId: UUID):
    """LOST-03: get lost report. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "LOST-03 구현 예정"},
    )


@router.put('/lost-reports/{reportId}', summary='update lost report', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def update_lost_report(reportId: UUID):
    """LOST-04: update lost report. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "LOST-04 구현 예정"},
    )


@router.post('/lost-reports/{reportId}/extend', summary='extend lost report', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def extend_lost_report(reportId: UUID):
    """LOST-05: extend lost report. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "LOST-05 구현 예정"},
    )


@router.post('/lost-reports/{reportId}/resolve', summary='resolve lost report', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def resolve_lost_report(reportId: UUID):
    """LOST-06: resolve lost report. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "LOST-06 구현 예정"},
    )
