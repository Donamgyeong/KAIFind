"""Profile HTTP acceptance tests with real PostgreSQL and authentication."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from router.auth import router as auth_router
from router.profile import router


BASE = '/api/v1/me/profile'
AUTH = '/api/v1/auth'


@pytest.fixture
def client(auth_runtime):
    app = FastAPI()
    app.state.auth_runtime = auth_runtime
    app.include_router(auth_router, prefix='/api/v1')
    app.include_router(router, prefix='/api/v1')
    with TestClient(app, base_url='https://testserver') as client:
        yield client


def login(client, role='MEMBER'):
    csrf = client.get(AUTH + '/csrf').json()['csrfToken']
    accounts = client.get(AUTH + '/mock/accounts').json()['accounts']
    account = next(account for account in accounts if account['role'] == role)
    response = client.post(
        AUTH + '/mock/login',
        json={'mockAccountId': account['mockAccountId']},
        headers={'X-CSRF-Token': csrf},
    )
    assert response.status_code == 200, response.text
    return response.json()


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert set(response.json()) == {'code', 'message', 'fieldErrors'}
    assert response.json()['code'] == code
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('role', ['MEMBER', 'ADMIN'])
def test_profile_update_persists_across_auth_and_login(client, role):
    logged_in = login(client, role)
    original = logged_in['user']
    response = client.get(BASE)
    assert response.status_code == 200
    assert response.json() == original
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['content-language'] == 'ko'

    expected = {**original, 'language': 'en'}
    for _ in range(2):
        response = client.patch(
            BASE, json={'language': ' en '},
            headers={'X-CSRF-Token': logged_in['csrfToken'], 'Accept-Language': 'ko'},
        )
        assert response.status_code == 200, response.text
        assert response.json() == expected
        assert response.headers['content-language'] == 'ko'
        assert response.headers['cache-control'] == 'no-store'
    assert client.get(BASE).json() == expected
    assert client.get(AUTH + '/me').json() == expected
    assert login(client, role)['user'] == expected

    # A separate account retains its own language and identity.
    other = login(client, 'ADMIN' if role == 'MEMBER' else 'MEMBER')['user']
    assert other['userId'] != original['userId']
    assert other['language'] == 'ko'
    assert client.get(BASE).json() == other


@pytest.mark.parametrize('method', ['GET', 'PATCH'])
@pytest.mark.parametrize('session', ['missing', 'unknown', 'anonymous', 'expired'])
def test_authentication_required(client, auth_runtime, method, session):
    if session == 'unknown':
        client.cookies.set('KAIFIND_SESSION', 'unknown')
    elif session == 'anonymous':
        client.get(AUTH + '/csrf')
    elif session == 'expired':
        login(client)
        auth_runtime.clock.advance(minutes=31)
    response = client.request(method, BASE, headers={'Accept-Language': 'en'})
    assert_error(response, 401, 'SESSION_EXPIRED' if session == 'expired' else 'AUTH_REQUIRED')
    assert response.headers['content-language'] == 'en'
    if session == 'expired':
        assert not client.cookies.get('KAIFIND_SESSION')


@pytest.mark.parametrize('body,field', [
    ({}, 'language'), ({'language': None}, 'language'),
    ({'language': 1}, 'language'), ({'language': True}, 'language'),
    ({'language': 'ja'}, 'language'), ({'language': ' '}, 'language'),
    *[({'language': 'en', field: 'changed'}, field)
      for field in ('userId', 'name', 'email', 'affiliation', 'role')],
])
def test_invalid_update_preserves_profile(client, body, field):
    logged_in = login(client)
    response = client.patch(BASE, json=body, headers={'X-CSRF-Token': logged_in['csrfToken']})
    assert_error(response, 400, 'VALIDATION_ERROR')
    assert any(error['field'] == field for error in response.json()['fieldErrors'])
    assert client.get(BASE).json() == logged_in['user']


@pytest.mark.parametrize('case,status,code', [
    ('missing_csrf', 403, 'CSRF_INVALID'),
    ('invalid_csrf', 403, 'CSRF_INVALID'),
    ('origin', 403, 'ORIGIN_NOT_ALLOWED'),
    ('media', 415, 'UNSUPPORTED_MEDIA_TYPE'),
    ('missing_media', 415, 'UNSUPPORTED_MEDIA_TYPE'),
    ('json', 400, 'MALFORMED_JSON'),
])
def test_write_guards_preserve_profile(client, case, status, code):
    logged_in = login(client)
    headers = {'X-CSRF-Token': logged_in['csrfToken'], 'Content-Type': 'application/json'}
    content = '{"language":"en"}'
    if case == 'missing_csrf':
        del headers['X-CSRF-Token']
    elif case == 'invalid_csrf':
        headers['X-CSRF-Token'] = 'incorrect'
    elif case == 'origin':
        headers['Origin'] = 'https://untrusted.example.com'
    elif case == 'media':
        headers['Content-Type'] = 'text/plain'
    elif case == 'missing_media':
        del headers['Content-Type']
    elif case == 'json':
        content = '{'

    response = client.patch(BASE, content=content, headers=headers)
    assert_error(response, status, code)
    assert client.get(BASE).json() == logged_in['user']
