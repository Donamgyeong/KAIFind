"""Auth HTTP endpoints; session transactions belong to AuthService."""
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from library.auth_http import AuthRoute
from schema.auth import (AuthUserResponse, CsrfTokenResponse, LoginResponse,
                         MockAccountListResponse, MockLoginRequest)
from schema.common import ErrorResponse
from service.auth import AuthService, clear_cookie, runtime, set_cookie
from .auth_params import AuthParams, CsrfParams, LogoutParams, MockLoginParams, SessionParams

router = APIRouter(tags=['auth'], route_class=AuthRoute,
                   responses={'default': {'model': ErrorResponse, 'description': '공통 오류'}})


def errors(*codes):
    return {code: {'model': ErrorResponse} for code in codes}


@router.get('/auth/csrf', summary='CSRF 토큰 발급·조회', response_model=CsrfTokenResponse,
            responses=errors(500))
async def get_csrf_token(request: Request, response: Response, params: Annotated[CsrfParams, Depends()]):
    csrf, token = await AuthService(runtime(request)).csrf(params.session)
    if token:
        set_cookie(response, token)
    return dict(csrfToken=csrf, headerName='X-CSRF-Token')


@router.get('/auth/me', summary='로그인한 본인 조회', response_model=AuthUserResponse,
            responses=errors(401, 500))
async def get_current_user(request: Request, params: Annotated[SessionParams, Depends()]):
    return await AuthService(runtime(request)).me(params.session)


@router.post('/auth/logout', summary='현재 세션 로그아웃', status_code=204,
             response_class=Response, responses=errors(403, 500))
async def logout(request: Request, params: Annotated[LogoutParams, Depends()]):
    await AuthService(runtime(request)).logout(params.session, params.csrf_token)
    response = Response(status_code=204)
    clear_cookie(response)
    return response


@router.get('/auth/mock/accounts', summary='선택 가능한 가상 계정 조회',
            response_model=MockAccountListResponse, responses=errors(404, 500))
async def list_mock_accounts(request: Request, params: Annotated[AuthParams, Depends()]):
    return dict(accounts=await AuthService(runtime(request)).accounts())


@router.post('/auth/mock/login', summary='선택 계정 로그인', response_model=LoginResponse,
             responses=errors(400, 401, 403, 404, 415, 429, 500))
async def mock_login(request: Request, response: Response, body: MockLoginRequest,
                     params: Annotated[MockLoginParams, Depends()]):
    payload, token = await AuthService(runtime(request)).login(params.session, params.csrf_token, body.mock_account_id)
    set_cookie(response, token)
    return payload
