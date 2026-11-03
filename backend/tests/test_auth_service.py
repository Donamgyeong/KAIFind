"""PostgreSQL integration checks for expiry, races and transaction rollback."""
import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, update

from model import Session, User
from router.auth import router
from service.auth import AuthError, AuthService, token_hash


@pytest.fixture
def client(auth_runtime):
    app = FastAPI()
    app.state.auth_runtime = auth_runtime
    app.include_router(router, prefix='/api/v1')
    with TestClient(app, base_url='https://testserver') as client:
        yield client


BASE = '/api/v1/auth'


def sign_in(client, key='student-01'):
    csrf = client.get(BASE + '/csrf').json()['csrfToken']
    response = client.post(BASE + '/mock/login', json={'mockAccountId': key}, headers={'X-CSRF-Token': csrf})
    assert response.status_code == 200, response.text
    return response.json()


def session_row(rt, cookie):
    with rt.sync_engine.connect() as db:
        return db.execute(select(Session.__table__).where(Session.token_hash == token_hash(cookie))).mappings().one_or_none()


@pytest.mark.parametrize('seconds,expected', [(1799, 200), (1800, 401), (1801, 401)])
def test_idle_expiry_boundary(client, auth_runtime, seconds, expected):
    sign_in(client)
    cookie = client.cookies.get('KAIFIND_SESSION')
    auth_runtime.clock.advance(seconds=seconds)
    response = client.get(BASE + '/me')
    assert response.status_code == expected
    if expected == 401:
        assert response.json()['code'] == 'SESSION_EXPIRED'
        assert 'max-age=0' in response.headers['set-cookie'].lower()
        assert session_row(auth_runtime, cookie) is None
        client.cookies.set('KAIFIND_SESSION', cookie)
        assert client.get(BASE + '/me').json()['code'] == 'AUTH_REQUIRED'


@pytest.mark.parametrize('seconds,expected', [(43199, 200), (43200, 401), (43201, 401)])
def test_absolute_expiry_boundary(client, auth_runtime, seconds, expected):
    sign_in(client)
    cookie = client.cookies.get('KAIFIND_SESSION')
    # Keep idle validity beyond the absolute boundary to isolate absolute expiry.
    with auth_runtime.sync_engine.begin() as db:
        db.execute(update(Session).values(idle_expires_at=auth_runtime.clock() + timedelta(hours=13)))
    auth_runtime.clock.advance(seconds=seconds)
    response = client.get(BASE + '/me')
    assert response.status_code == expected
    row = session_row(auth_runtime, cookie)
    if expected == 200:
        assert row['idle_expires_at'] == row['absolute_expires_at']
    else:
        assert response.json()['code'] == 'SESSION_EXPIRED'
        assert row is None


def test_protected_activity_extends_idle_only(client, auth_runtime):
    sign_in(client)
    cookie = client.cookies.get('KAIFIND_SESSION')
    before = session_row(auth_runtime, cookie)
    auth_runtime.clock.advance(minutes=20)
    assert client.get(BASE + '/me').status_code == 200
    after = session_row(auth_runtime, cookie)
    assert after['last_activity_at'] == auth_runtime.clock()
    assert after['idle_expires_at'] == auth_runtime.clock() + timedelta(minutes=30)
    assert after['absolute_expires_at'] == before['absolute_expires_at']


def test_public_reads_do_not_refresh_activity(client, auth_runtime):
    sign_in(client)
    cookie = client.cookies.get('KAIFIND_SESSION')
    before = session_row(auth_runtime, cookie)
    auth_runtime.clock.advance(minutes=10)
    assert client.get(BASE + '/csrf').status_code == 200
    assert client.get(BASE + '/mock/accounts').status_code == 200
    assert session_row(auth_runtime, cookie) == before


def test_expired_csrf_session_is_replaced(client, auth_runtime):
    old = client.get(BASE + '/csrf').json()['csrfToken']
    cookie = client.cookies.get('KAIFIND_SESSION')
    auth_runtime.clock.advance(minutes=30)
    new = client.get(BASE + '/csrf')
    assert new.status_code == 200
    assert new.json()['csrfToken'] != old
    assert client.cookies.get('KAIFIND_SESSION') != cookie
    assert session_row(auth_runtime, cookie) is None


@pytest.mark.parametrize('path', ['/mock/login', '/logout'])
def test_expired_session_rejects_state_changes(client, auth_runtime, path):
    token = client.get(BASE + '/csrf').json()['csrfToken']
    auth_runtime.clock.advance(minutes=30)
    kwargs = {'json': {'mockAccountId': 'student-01'}} if path == '/mock/login' else {}
    response = client.post(BASE + path, headers={'X-CSRF-Token': token}, **kwargs)
    assert response.status_code == 403
    assert response.json()['code'] == 'CSRF_INVALID'


def test_current_role_and_language_survive_relogin(client, auth_runtime):
    first = sign_in(client)
    assert first['isNewUser'] is True
    with auth_runtime.sync_engine.begin() as db:
        db.execute(update(User).values(role='ADMIN', language='en'))
    assert client.get(BASE + '/me').json()['role'] == 'ADMIN'
    accounts = client.get(BASE + '/mock/accounts').json()['accounts']
    assert next(a for a in accounts if a['mockAccountId'] == 'student-01')['role'] == 'ADMIN'
    second = sign_in(client)
    assert second['user']['userId'] == first['user']['userId']
    assert second['user']['role'] == 'ADMIN'
    assert second['user']['language'] == 'en'
    assert second['isNewUser'] is False
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1


def test_account_switch_and_admin_seed(client):
    first = sign_in(client)
    second = sign_in(client, 'admin-01')
    assert first['user']['userId'] != second['user']['userId']
    assert second['user']['role'] == 'ADMIN'
    assert client.get(BASE + '/me').json() == second['user']


@pytest.mark.parametrize('environment,enabled', [('production', True), ('test', False)])
def test_mock_disabled_even_with_invalid_body(client, auth_runtime, environment, enabled):
    auth_runtime.settings = replace(auth_runtime.settings, environment=environment, mock_enabled=enabled)
    for response in [client.get(BASE + '/mock/accounts'), client.post(BASE + '/mock/login', content='{')]:
        assert response.status_code == 404
        assert response.json()['code'] == 'MOCK_AUTH_DISABLED'


def test_empty_registry_and_disabled_account(client, auth_runtime):
    token = client.get(BASE + '/csrf').json()['csrfToken']
    auth_runtime.settings = replace(auth_runtime.settings,
        accounts=tuple(replace(a, active=False) for a in auth_runtime.settings.accounts))
    assert client.get(BASE + '/mock/accounts').json() == {'accounts': []}
    response = client.post(BASE + '/mock/login', json={'mockAccountId': 'student-01'},
        headers={'X-CSRF-Token': token})
    assert response.status_code == 401
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0


def test_login_rate_limit_and_reset(client, auth_runtime):
    for _ in range(30):
        assert client.post(BASE + '/mock/login', content='').status_code == 415
    response = client.post(BASE + '/mock/login', content='')
    assert response.status_code == 429
    assert response.json()['code'] == 'RATE_LIMITED'
    assert response.headers['retry-after'] == '60'
    auth_runtime.clock.advance(seconds=59)
    assert client.post(BASE + '/mock/login').headers['retry-after'] == '1'
    auth_runtime.clock.advance(seconds=1)
    assert client.post(BASE + '/mock/login').status_code == 415


def test_csrf_is_encrypted_and_session_is_hashed(client, auth_runtime):
    token = client.get(BASE + '/csrf').json()['csrfToken']
    cookie = client.cookies.get('KAIFIND_SESSION')
    row = session_row(auth_runtime, cookie)
    assert row['token_hash'] != cookie
    assert token not in row['csrf_secret_ciphertext']
    assert AuthService(auth_runtime).decrypt(row['csrf_secret_ciphertext']) == token


def test_failed_session_insert_rolls_back_user_and_keeps_old_login(client, auth_runtime):
    first = sign_in(client)
    cookie = client.cookies.get('KAIFIND_SESSION')
    def fail(*args):
        raise RuntimeError('sensitive database detail')
    event.listen(Session, 'before_insert', fail)
    try:
        response = client.post(BASE + '/mock/login', json={'mockAccountId': 'admin-01'},
            headers={'X-CSRF-Token': first['csrfToken']})
    finally:
        event.remove(Session, 'before_insert', fail)
    assert response.status_code == 500
    assert response.json()['code'] == 'INTERNAL_SERVER_ERROR'
    assert 'sensitive' not in response.text
    assert 'set-cookie' not in response.headers
    assert client.cookies.get('KAIFIND_SESSION') == cookie
    assert client.get(BASE + '/me').json() == first['user']
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.asyncio
async def test_concurrent_first_login_has_one_user(auth_runtime):
    service = AuthService(auth_runtime)
    sessions = await asyncio.gather(service.csrf(None), service.csrf(None))
    results = await asyncio.gather(*(service.login(cookie, csrf, 'student-01') for csrf, cookie in sessions))
    assert sum(payload['isNewUser'] for payload, _ in results) == 1
    assert len({payload['user'].user_id for payload, _ in results}) == 1
    for payload, cookie in results:
        assert (await service.me(cookie)).user_id == payload['user'].user_id
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Session)) == 2


@pytest.mark.asyncio
async def test_atomic_rate_limit_across_workers_and_ips(auth_runtime):
    async def attempt(ip):
        try:
            await AuthService(auth_runtime).rate_limit(ip)
            return 200
        except AuthError as exc:
            return exc.status
    results = await asyncio.gather(*(attempt('192.0.2.1') for _ in range(35)))
    assert results.count(200) == 30
    assert results.count(429) == 5
    assert await attempt('192.0.2.2') == 200


@pytest.mark.asyncio
async def test_logout_and_activity_race_cannot_resurrect_session(auth_runtime):
    service = AuthService(auth_runtime)
    csrf, anonymous = await service.csrf(None)
    payload, cookie = await service.login(anonymous, csrf, 'student-01')
    results = await asyncio.gather(service.logout(cookie, payload['csrfToken']), service.me(cookie),
                                   return_exceptions=True)
    assert results[0] is None
    assert results[1] is not None
    assert session_row(auth_runtime, cookie) is None
    with pytest.raises(AuthError) as exc:
        await service.me(cookie)
    assert exc.value.code == 'AUTH_REQUIRED'


@pytest.mark.parametrize('origin', [None, 'https://testserver'])
def test_allowed_or_missing_origin_and_json_charset(client, origin):
    csrf = client.get(BASE + '/csrf').json()['csrfToken']
    headers = {'X-CSRF-Token': csrf, 'Content-Type': 'application/json; charset=utf-8'}
    if origin:
        headers['Origin'] = origin
    response = client.post(BASE + '/mock/login', content='{"mockAccountId":"student-01"}', headers=headers)
    assert response.status_code == 200


def test_validation_message_changes_language_but_not_codes(client):
    csrf = client.get(BASE + '/csrf').json()['csrfToken']
    bodies = []
    for language in ['ko', 'en']:
        response = client.post(BASE + '/mock/login', json={'mockAccountId': None},
            headers={'X-CSRF-Token': csrf, 'Accept-Language': language})
        assert response.status_code == 400
        assert response.headers['content-language'] == language
        bodies.append(response.json())
    assert bodies[0]['code'] == bodies[1]['code'] == 'VALIDATION_ERROR'
    assert bodies[0]['message'] != bodies[1]['message']
    assert bodies[0]['fieldErrors'][0]['code'] == bodies[1]['fieldErrors'][0]['code'] == 'INVALID_TYPE'
    assert bodies[0]['fieldErrors'][0]['message'] != bodies[1]['fieldErrors'][0]['message']


@pytest.mark.asyncio
async def test_unicode_csrf_is_rejected_as_auth_error(auth_runtime):
    service = AuthService(auth_runtime)
    _, cookie = await service.csrf(None)
    with pytest.raises(AuthError) as exc:
        await service.logout(cookie, '위조된-토큰')
    assert exc.value.code == 'CSRF_INVALID'


def test_missing_encryption_key_is_a_sanitized_configuration_error(client, auth_runtime):
    auth_runtime.settings = replace(auth_runtime.settings, encryption_key=b'')
    response = client.get(BASE + '/csrf')
    assert response.status_code == 500
    assert response.json()['code'] == 'INTERNAL_SERVER_ERROR'
    assert 'AUTH_ENCRYPTION_KEY' not in response.text


def test_main_application_mounts_real_auth_routes(auth_runtime):
    from main import app
    app.state.auth_runtime = auth_runtime
    try:
        with TestClient(app, base_url='https://testserver') as client:
            user = sign_in(client)
            assert client.get(BASE + '/me').json() == user['user']
    finally:
        del app.state.auth_runtime
