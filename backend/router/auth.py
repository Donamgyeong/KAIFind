"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["auth"])


@router.get('/auth/csrf', summary='CSRF 토큰 발급·조회', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def get_csrf_token():
    """AUTH-01: CSRF 토큰 발급·조회. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "AUTH-01 구현 예정"},
    )


@router.get('/auth/me', summary='로그인한 본인 조회', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def get_current_user():
    """AUTH-04: 로그인한 본인 조회. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "AUTH-04 구현 예정"},
    )


@router.post('/auth/logout', summary='현재 세션 로그아웃', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def logout():
    """AUTH-05: 현재 세션 로그아웃. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "AUTH-05 구현 예정"},
    )


@router.get('/auth/mock/accounts', summary='선택 가능한 가상 계정 조회', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_mock_accounts():
    """AUTH-02: 선택 가능한 가상 계정 조회. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "AUTH-02 구현 예정"},
    )


@router.post('/auth/mock/login', summary='선택 계정 로그인', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def mock_login():
    """AUTH-03: 선택 계정 로그인. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "AUTH-03 구현 예정"},
    )
