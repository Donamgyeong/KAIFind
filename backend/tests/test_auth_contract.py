"""Public HTTP acceptance tests.

Strict xfail marks pending service behavior: an implemented case becomes XPASS
and fails the run until its marker is removed. Never mock the auth handlers.
The current app has no configurable clock, mock-account registry or repository;
DB rollback, expiry boundaries and concurrency need those seams before testing.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from router.auth import router

pending = pytest.mark.xfail(strict=True, raises=AssertionError,
                            reason='Auth service and error translation are not implemented')
BASE = '/api/v1/auth'
COOKIE = 'KAIFIND_SESSION'


@pytest.fixture
def client():
    # Mount the real router without importing unrelated ORM/database dependencies.
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    with TestClient(app, base_url='https://testserver') as client:
        yield client


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {'code', 'message', 'fieldErrors'}
    assert body['code'] == code
    assert isinstance(body['message'], str) and body['message']
    assert isinstance(body['fieldErrors'], list)
    for error in body['fieldErrors']:
        assert set(error) == {'field', 'code', 'message'}


def csrf(client):
    response = client.get(BASE + '/csrf')
    assert response.status_code == 200, response.text
    assert response.json()['headerName'] == 'X-CSRF-Token'
    assert client.cookies.get(COOKIE)
    return response.json()['csrfToken']


def login(client):
    token = csrf(client)
    accounts = client.get(BASE + '/mock/accounts')
    assert accounts.status_code == 200
    assert accounts.json()['accounts'], 'Test environment needs an active seeded mock account'
    key = accounts.json()['accounts'][0]['mockAccountId']
    response = client.post(BASE + '/mock/login', json={'mockAccountId': key},
                           headers={'X-CSRF-Token': token})
    assert response.status_code == 200, response.text
    return response


@pending
def test_csrf_creates_secure_anonymous_cookie(client):
    response = client.get(BASE + '/csrf')
    assert response.status_code == 200
    assert set(response.json()) == {'csrfToken', 'headerName'}
    assert response.json()['csrfToken']
    cookie = response.headers['set-cookie'].lower()
    for attribute in ['httponly', 'secure', 'samesite=lax', 'path=/']:
        assert attribute in cookie
    for attribute in ['domain=', 'expires=', 'max-age=']:
        assert attribute not in cookie


@pending
def test_csrf_reuses_session_and_token(client):
    token = csrf(client)
    session = client.cookies.get(COOKIE)
    assert csrf(client) == token
    assert client.cookies.get(COOKIE) == session
    assert_error(client.get(BASE + '/me'), 401, 'AUTH_REQUIRED')


@pending
def test_unknown_cookie_replaced_with_anonymous_session(client):
    client.cookies.set(COOKIE, 'unknown-session', domain='testserver.local', path='/')
    csrf(client)
    assert client.cookies.get(COOKIE) != 'unknown-session'


@pending
def test_account_list_exposes_only_public_fields(client):
    response = client.get(BASE + '/mock/accounts')
    assert response.status_code == 200
    assert set(response.json()) == {'accounts'}
    for account in response.json()['accounts']:
        assert set(account) == {'mockAccountId', 'displayName', 'affiliation', 'role'}
        assert account['role'] in {'MEMBER', 'ADMIN'}
        assert account['affiliation'] in {'STUDENT', 'FACULTY', 'STAFF'}


@pytest.mark.parametrize('cookie', [None, 'unknown-session'])
@pending
def test_me_requires_authenticated_session(client, cookie):
    if cookie:
        client.cookies.set(COOKIE, cookie)
    assert_error(client.get(BASE + '/me'), 401, 'AUTH_REQUIRED')


@pytest.mark.parametrize('payload,field,code', [
    ({}, 'mockAccountId', 'REQUIRED'),
    ({'mockAccountId': None}, 'mockAccountId', 'INVALID_TYPE'),
    ({'mockAccountId': 12}, 'mockAccountId', 'INVALID_TYPE'),
    ({'mockAccountId': ''}, 'mockAccountId', 'INVALID_FORMAT'),
    ({'mockAccountId': 'Student'}, 'mockAccountId', 'INVALID_FORMAT'),
    *[({'mockAccountId': 'student-01', field: 'ADMIN'}, field, 'UNKNOWN_FIELD')
      for field in ['role', 'email', 'name', 'userId', 'affiliation']],
])
@pending
def test_login_field_errors(client, payload, field, code):
    token = csrf(client)
    response = client.post(BASE + '/mock/login', json=payload, headers={'X-CSRF-Token': token})
    assert_error(response, 400, 'VALIDATION_ERROR')
    assert any(e['field'] == field and e['code'] == code for e in response.json()['fieldErrors'])


@pytest.mark.parametrize('body', ['', '{', '{"mockAccountId":'])
@pending
def test_malformed_json(client, body):
    token = csrf(client)
    response = client.post(BASE + '/mock/login', content=body,
        headers={'Content-Type': 'application/json', 'X-CSRF-Token': token})
    assert_error(response, 400, 'MALFORMED_JSON')


@pytest.mark.parametrize('content_type', [None, 'text/plain'])
@pending
def test_login_requires_json_media_type(client, content_type):
    token = csrf(client)
    headers = {'X-CSRF-Token': token}
    if content_type:
        headers['Content-Type'] = content_type
    response = client.post(BASE + '/mock/login', content='{"mockAccountId":"student-01"}', headers=headers)
    assert_error(response, 415, 'UNSUPPORTED_MEDIA_TYPE')


@pytest.mark.parametrize('path', ['/mock/login', '/logout'])
@pytest.mark.parametrize('token', [None, '', 'incorrect-token'])
@pending
def test_writes_reject_missing_or_invalid_csrf(client, path, token):
    csrf(client)
    headers = {} if token is None else {'X-CSRF-Token': token}
    kwargs = {'json': {'mockAccountId': 'student-01'}} if path == '/mock/login' else {}
    assert_error(client.post(BASE + path, headers=headers, **kwargs), 403, 'CSRF_INVALID')


@pending
def test_login_rotates_session_and_me_matches_response(client):
    old_token = csrf(client)
    old_session = client.cookies.get(COOKIE)
    response = login(client)
    data = response.json()
    assert set(data) == {'user', 'isNewUser', 'session', 'csrfToken'}
    assert isinstance(data['isNewUser'], bool)
    assert client.cookies.get(COOKIE) != old_session
    assert data['csrfToken'] != old_token
    assert client.get(BASE + '/me').json() == data['user']
    assert_error(client.post(BASE + '/logout', headers={'X-CSRF-Token': old_token}), 403, 'CSRF_INVALID')
    client.cookies.clear()
    client.cookies.set(COOKIE, old_session)
    assert_error(client.get(BASE + '/me'), 401, 'AUTH_REQUIRED')


@pending
def test_invalid_account_preserves_existing_login(client):
    logged_in = login(client).json()
    session = client.cookies.get(COOKIE)
    response = client.post(BASE + '/mock/login', json={'mockAccountId': 'missing-account-for-test'},
        headers={'X-CSRF-Token': logged_in['csrfToken']})
    assert_error(response, 401, 'INVALID_MOCK_ACCOUNT')
    assert client.cookies.get(COOKIE) == session
    assert client.get(BASE + '/me').json() == logged_in['user']


@pytest.mark.parametrize('authenticated', [False, True])
@pending
def test_logout_deletes_session_and_returns_no_body(client, authenticated):
    token = login(client).json()['csrfToken'] if authenticated else csrf(client)
    session = client.cookies.get(COOKIE)
    response = client.post(BASE + '/logout', headers={'X-CSRF-Token': token})
    assert response.status_code == 204
    assert response.content == b''
    cookie = response.headers['set-cookie'].lower()
    for attr in ['max-age=0', 'path=/', 'secure', 'httponly', 'samesite=lax']:
        assert attr in cookie
    assert not client.cookies.get(COOKIE)
    client.cookies.set(COOKIE, session)
    assert_error(client.get(BASE + '/me'), 401, 'AUTH_REQUIRED')
    assert_error(client.post(BASE + '/logout', headers={'X-CSRF-Token': token}), 403, 'CSRF_INVALID')


@pytest.mark.parametrize('method,path', [('GET', '/csrf'), ('GET', '/mock/accounts'),
    ('GET', '/me'), ('POST', '/mock/login'), ('POST', '/logout')])
@pending
def test_all_auth_responses_disable_caching(client, method, path):
    response = client.request(method, BASE + path)
    assert response.headers.get('cache-control') == 'no-store'


@pytest.mark.parametrize('language,expected', [('ko', 'ko'), ('en', 'en'), ('ja', 'ko'), (None, 'ko')])
@pending
def test_error_language_and_shape(client, language, expected):
    headers = {} if language is None else {'Accept-Language': language}
    response = client.get(BASE + '/me', headers=headers)
    assert_error(response, 401, 'AUTH_REQUIRED')
    assert response.headers['content-language'] == expected


@pytest.mark.parametrize('path', ['/mock/login', '/logout'])
@pending
def test_disallowed_origin_preserves_session(client, path):
    token = csrf(client)
    session = client.cookies.get(COOKIE)
    kwargs = {'json': {'mockAccountId': 'student-01'}} if path == '/mock/login' else {}
    response = client.post(BASE + path,
        headers={'X-CSRF-Token': token, 'Origin': 'https://untrusted.example.com'}, **kwargs)
    assert_error(response, 403, 'ORIGIN_NOT_ALLOWED')
    assert client.cookies.get(COOKIE) == session
    assert csrf(client) == token


@pending
def test_token_from_another_browser_is_rejected(client):
    own_token = csrf(client)
    with TestClient(client.app, base_url='https://testserver') as other:
        csrf(other)
        response = other.post(BASE + '/logout', headers={'X-CSRF-Token': own_token})
        assert_error(response, 403, 'CSRF_INVALID')
    assert csrf(client) == own_token


@pending
def test_repeat_login_keeps_user_id(client):
    first = login(client).json()
    second = login(client).json()
    assert first['user']['userId'] == second['user']['userId']
    assert second['isNewUser'] is False
    assert first['csrfToken'] != second['csrfToken']


@pending
def test_logout_does_not_revoke_other_browser(client):
    first = login(client).json()
    first_session = client.cookies.get(COOKIE)
    client.cookies.clear()
    second = login(client).json()
    assert second['user']['userId'] == first['user']['userId']
    response = client.post(BASE + '/logout', headers={'X-CSRF-Token': second['csrfToken']})
    assert response.status_code == 204
    client.cookies.set(COOKIE, first_session)
    response = client.get(BASE + '/me')
    assert response.status_code == 200
    assert response.json() == first['user']
