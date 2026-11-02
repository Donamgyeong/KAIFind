"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["admin"])


@router.get('/admin/users', summary='권한 관리용 회원 조회', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_users():
    """ADM-01: 권한 관리용 회원 조회. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ADM-01 구현 예정"},
    )


@router.patch('/admin/users/{userId}/role', summary='관리자 권한 부여·회수', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def update_user_role(userId: UUID):
    """ADM-02: 관리자 권한 부여·회수. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ADM-02 구현 예정"},
    )


@router.get('/admin/buildings', summary='건물 전체 목록', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_buildings():
    """REF-01: 건물 전체 목록. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "REF-01 구현 예정"},
    )


@router.post('/admin/buildings', summary='건물 추가', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def create_building():
    """REF-02: 건물 추가. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "REF-02 구현 예정"},
    )


@router.patch('/admin/buildings/{buildingId}', summary='건물 이름 변경·비활성화', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def update_building(buildingId: UUID):
    """REF-03: 건물 이름 변경·비활성화. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "REF-03 구현 예정"},
    )


@router.get('/admin/categories', summary='카테고리 전체 목록', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_categories():
    """REF-04: 카테고리 전체 목록. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "REF-04 구현 예정"},
    )


@router.post('/admin/categories', summary='카테고리 추가', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def create_category():
    """REF-05: 카테고리 추가. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "REF-05 구현 예정"},
    )


@router.patch('/admin/categories/{categoryId}', summary='카테고리 이름 변경·비활성화', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def update_category(categoryId: UUID):
    """REF-06: 카테고리 이름 변경·비활성화. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "REF-06 구현 예정"},
    )


@router.get('/admin/post-reports', summary='게시물 신고 목록', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_post_reports():
    """MOD-02: 게시물 신고 목록. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "MOD-02 구현 예정"},
    )


@router.get('/admin/post-reports/{reportId}', summary='게시물 신고 상세', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def get_post_report(reportId: UUID):
    """MOD-03: 게시물 신고 상세. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "MOD-03 구현 예정"},
    )


@router.post('/admin/post-reports/{reportId}/review', summary='신고 검토·숨김', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def review_post_report(reportId: UUID):
    """MOD-04: 신고 검토·숨김. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "MOD-04 구현 예정"},
    )


@router.get('/admin/disputes', summary='수거 분쟁 목록', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_disputes():
    """ADS-01: 수거 분쟁 목록. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ADS-01 구현 예정"},
    )


@router.get('/admin/disputes/{disputeId}', summary='수거 분쟁 상세', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def get_dispute(disputeId: UUID):
    """ADS-02: 수거 분쟁 상세. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ADS-02 구현 예정"},
    )


@router.post('/admin/disputes/{disputeId}/review', summary='수거 분쟁 검토', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def review_dispute(disputeId: UUID):
    """ADS-03: 수거 분쟁 검토. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ADS-03 구현 예정"},
    )


@router.put('/admin/users/{userId}/collection-restriction', summary='수거 권한 제한·해제', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def update_collection_restriction(userId: UUID):
    """ADS-04: 수거 권한 제한·해제. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "ADS-04 구현 예정"},
    )


@router.get('/admin/statistics', summary='상태별 기본 통계', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def get_statistics():
    """STA-01: 상태별 기본 통계. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "STA-01 구현 예정"},
    )


@router.get('/admin/audit-logs', summary='감사 로그 조회', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_audit_logs():
    """AUD-01: 감사 로그 조회. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "AUD-01 구현 예정"},
    )
