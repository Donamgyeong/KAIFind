"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from schema.auth import (AuthUserResponse, CsrfTokenResponse,
                         LoginResponse, MockAccountListResponse, MockLoginRequest)
from schema.common import ErrorResponse
from .auth_params import AuthParams, CsrfParams, LogoutParams, MockLoginParams, SessionParams

router = APIRouter(tags=["auth"])


def error_responses(*codes: int) -> dict:
    return {code: {"model": ErrorResponse} for code in codes}


@router.get('/auth/csrf', summary='CSRF 토큰 발급·조회', response_model=CsrfTokenResponse, responses={**error_responses(500), 501: {"description": "아직 구현되지 않은 기능"}})
async def get_csrf_token(params: Annotated[CsrfParams, Depends()]):
    """AUTH-01: CSRF 토큰 발급·조회. 파라미터·DTO 정의 완료. 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "AUTH-01 구현 예정"},
    )


@router.get('/auth/me', summary='로그인한 본인 조회', response_model=AuthUserResponse, responses={**error_responses(401, 500), 501: {"description": "아직 구현되지 않은 기능"}})
async def get_current_user(params: Annotated[SessionParams, Depends()]):
    """AUTH-04: 로그인한 본인 조회. 파라미터·DTO 정의 완료. 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "AUTH-04 구현 예정"},
    )


@router.post('/auth/logout', summary='현재 세션 로그아웃', status_code=204, response_class=Response, responses={**error_responses(403, 500), 501: {"description": "아직 구현되지 않은 기능"}})
async def logout(params: Annotated[LogoutParams, Depends()]):
    """AUTH-05: 현재 세션 로그아웃. 파라미터·DTO 정의 완료. 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "AUTH-05 구현 예정"},
    )


@router.get('/auth/mock/accounts', summary='선택 가능한 가상 계정 조회', response_model=MockAccountListResponse, responses={**error_responses(404, 500), 501: {"description": "아직 구현되지 않은 기능"}})
async def list_mock_accounts(params: Annotated[AuthParams, Depends()]):
    """AUTH-02: 선택 가능한 가상 계정 조회. 파라미터·DTO 정의 완료. 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "AUTH-02 구현 예정"},
    )


@router.post('/auth/mock/login', summary='선택 계정 로그인', response_model=LoginResponse, responses={**error_responses(400, 401, 403, 404, 415, 429, 500), 501: {"description": "아직 구현되지 않은 기능"}})
async def mock_login(body: MockLoginRequest, params: Annotated[MockLoginParams, Depends()]):
    """AUTH-03: 선택 계정 로그인. 파라미터·DTO 정의 완료. 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "AUTH-03 구현 예정"},
    )
