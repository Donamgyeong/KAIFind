"""Protected bodyless writes retain real session, CSRF and transaction guards."""
from uuid import UUID

import pytest
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.testclient import TestClient
from sqlalchemy import text

from library.matching_lock import MATCHING_LOCK_NAMESPACE, category_lock_key, lock_matching_categories
from library.protected_http import ProtectedRoute
from router.auth import router as auth_router
from schema.common import ApiModel, ErrorResponse
from service.auth import AuthError
from test_admin_contract import error, login


class ActionBody(ApiModel):
    value: str


LOCKED_CATEGORY = UUID('12345678-1234-5678-1234-567812345678')


@pytest.fixture
def client(auth_runtime):
    app = FastAPI()
    app.state.auth_runtime = auth_runtime
    app.state.calls = 0
    app.include_router(auth_router, prefix='/api/v1')
    router = APIRouter(
        route_class=ProtectedRoute,
        responses={code: {'model': ErrorResponse} for code in (400, 401, 403, 415, 500)},
    )

    @router.post('/action')
    async def action(request: Request):
        request.app.state.calls += 1
        return {'ok': True}

    @router.delete('/action', status_code=204)
    async def remove(request: Request):
        request.app.state.calls += 1
        return Response(status_code=204)

    @router.post('/json')
    async def json_action(request: Request, body: ActionBody):
        request.app.state.calls += 1
        return body

    @router.post('/pending')
    async def pending():
        raise AuthError(409, 'MATCHING_PENDING')

    @router.post('/locked')
    async def locked(request: Request):
        await request.state.db.execute(text("SET LOCAL lock_timeout = '50ms'"))
        await lock_matching_categories(request.state.db, [LOCKED_CATEGORY])
        request.app.state.calls += 1
        return {'ok': True}

    # Exercise route cloning, as production routers pass through api_router.
    outer = APIRouter()
    outer.include_router(router)
    app.include_router(outer, prefix='/contract')
    with TestClient(app, base_url='https://testserver') as client:
        yield client


@pytest.mark.parametrize('method,status', [('POST', 200), ('DELETE', 204)])
def test_empty_write_needs_no_json_or_content_type(client, method, status):
    _, headers = login(client, 'student-01')
    response = client.request(method, '/contract/action', headers=headers)
    assert response.status_code == status, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['content-language'] == 'ko'
    assert client.app.state.calls == 1
    if status == 204:
        assert response.content == b''


@pytest.mark.parametrize('method', ['POST', 'DELETE'])
def test_bodyless_write_keeps_auth_csrf_and_origin_checks(client, method):
    error(client.request(method, '/contract/action'), 401, 'AUTH_REQUIRED')
    _, headers = login(client, 'student-01')
    error(client.request(method, '/contract/action'), 403, 'CSRF_INVALID')
    error(client.request(method, '/contract/action', headers={'X-CSRF-Token': 'invalid'}), 403, 'CSRF_INVALID')
    error(client.request(method, '/contract/action', headers={
        **headers, 'Origin': 'https://evil.example',
    }), 403, 'ORIGIN_NOT_ALLOWED')
    assert client.app.state.calls == 0


@pytest.mark.parametrize('method', ['POST', 'DELETE'])
@pytest.mark.parametrize('content', [b'{}', b'null', b'{', b' ', b'ignored'])
def test_bodyless_write_rejects_unexpected_body(client, method, content):
    _, headers = login(client, 'student-01')
    response = client.request(method, '/contract/action', content=content, headers={
        **headers, 'Content-Type': 'application/json', 'Accept-Language': 'en',
    })
    error(response, 400, 'VALIDATION_ERROR')
    assert response.headers['content-language'] == 'en'
    assert client.app.state.calls == 0


def test_declared_json_write_still_validates_media_json_and_fields(client):
    _, headers = login(client, 'student-01')
    error(client.post('/contract/json', content='{}', headers=headers), 415, 'UNSUPPORTED_MEDIA_TYPE')
    error(client.post('/contract/json', content='{', headers={
        **headers, 'Content-Type': 'application/json',
    }), 400, 'MALFORMED_JSON')
    error(client.post('/contract/json', json={'value': 'x', 'unknown': True}, headers=headers), 400, 'VALIDATION_ERROR')
    response = client.post('/contract/json', json={'value': 'x'}, headers=headers)
    assert response.status_code == 200 and response.json() == {'value': 'x'}
    assert client.app.state.calls == 1


def test_openapi_matches_body_contract_after_router_cloning(client):
    paths = client.get('/openapi.json').json()['paths']
    for method in ('post', 'delete'):
        operation = paths['/contract/action'][method]
        assert 'requestBody' not in operation
        names = [(p['in'], p['name']) for p in operation['parameters']]
        assert ('header', 'X-CSRF-Token') in names
        assert ('header', 'Content-Type') not in names
        assert len(names) == len(set(names))
    operation = paths['/contract/json']['post']
    headers = [p for p in operation['parameters'] if p['name'] == 'Content-Type']
    assert len(headers) == 1 and headers[0]['required'] is True
    assert 'application/json' in operation['requestBody']['content']
    assert 'content' not in paths['/contract/action']['delete']['responses']['204']


@pytest.mark.parametrize('language,word', [('ko', '비교'), ('en', 'matching')])
def test_matching_pending_has_localized_error_contract(client, language, word):
    _, headers = login(client, 'student-01')
    response = client.post('/contract/pending', headers={**headers, 'Accept-Language': language})
    error(response, 409, 'MATCHING_PENDING')
    assert word in response.json()['message']
    assert response.headers['content-language'] == language


def test_category_lock_timeout_returns_conflict_and_rolls_back(client, auth_runtime):
    _, headers = login(client, 'student-01')
    with auth_runtime.sync_engine.begin() as owner:
        owner.execute(text('SELECT pg_advisory_xact_lock(:namespace, :category)'), {
            'namespace': MATCHING_LOCK_NAMESPACE, 'category': category_lock_key(LOCKED_CATEGORY),
        })
        response = client.post('/contract/locked', headers=headers)
        error(response, 409, 'CONCURRENT_MODIFICATION')
        assert client.app.state.calls == 0
    assert client.post('/contract/locked', headers=headers).status_code == 200
    assert client.app.state.calls == 1
