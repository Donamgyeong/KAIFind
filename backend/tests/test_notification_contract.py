"""Notification HTTP contracts against disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from router.auth import router as auth_router
from router.notifications import router
from test_profile_contract import login, assert_error


SETTINGS = '/api/v1/me/notification-settings'
BASE = '/api/v1/me/notifications'
DEFAULTS = dict.fromkeys(
    ['emailEnabled', 'matchEmail', 'collectionEmail', 'expiryEmail', 'keywordEmail'], True,
)


@pytest.fixture
def client(auth_runtime):
    app = FastAPI()
    app.state.auth_runtime = auth_runtime
    app.include_router(auth_router, prefix='/api/v1')
    app.include_router(router, prefix='/api/v1')
    with TestClient(app, base_url='https://testserver') as client:
        yield client


def seed(rt, user_id, *, expired=False, read=False, kind='ITEM_EXPIRED'):
    notification_id = uuid4()
    with rt.sync_engine.begin() as db:
        db.execute(text('''
            INSERT INTO notifications
                (id,event_id,recipient_id,type,created_at,read_at,purge_after)
            VALUES (:id,:event,:user,:kind,:now,:read,:purge)
        '''), {
            'id': notification_id, 'event': uuid4(), 'user': user_id, 'kind': kind,
            'now': rt.clock(), 'read': rt.clock() if read else None,
            'purge': rt.clock() if expired else rt.clock().replace(year=2027),
        })
    return str(notification_id)


def test_settings_defaults_replace_and_isolation(client, auth_runtime):
    logged = login(client)
    assert client.get(SETTINGS).json() == DEFAULTS
    with auth_runtime.sync_engine.connect() as db:
        assert db.execute(text('SELECT count(*) FROM notification_settings')).scalar_one() == 0
    updated = {**DEFAULTS, 'emailEnabled': False, 'matchEmail': False}
    for _ in range(2):
        response = client.put(SETTINGS, json=updated, headers={'X-CSRF-Token': logged['csrfToken']})
        assert response.status_code == 200, response.text
        assert response.json() == updated
    assert client.get(SETTINGS).json() == updated
    login(client, 'ADMIN')
    assert client.get(SETTINGS).json() == DEFAULTS


@pytest.mark.parametrize('body', [{}, {**DEFAULTS, 'emailEnabled': None},
    {**DEFAULTS, 'matchEmail': 1}, {**DEFAULTS, 'expiryEmail': 'false'},
    {**DEFAULTS, 'extra': True}])
def test_invalid_settings(client, body):
    logged = login(client)
    assert_error(client.put(SETTINGS, json=body, headers={'X-CSRF-Token': logged['csrfToken']}),
                 400, 'VALIDATION_ERROR')
    assert client.get(SETTINGS).json() == DEFAULTS


def test_list_read_visibility_and_language(client, auth_runtime):
    logged = login(client)
    ids = [seed(auth_runtime, logged['user']['userId']) for _ in range(3)]
    expired = seed(auth_runtime, logged['user']['userId'], expired=True)
    response = client.get(BASE + '?size=2', headers={'Accept-Language': 'en'})
    assert response.status_code == 200, response.text
    page = response.json()
    assert page['totalElements'] == 3 and page['totalPages'] == 2
    assert [row['notificationId'] for row in page['items']] == sorted(ids, reverse=True)[:2]
    assert page['items'][0]['message'] == 'Your found item has expired.'
    assert page['items'][0]['createdAt'].endswith('+09:00')
    assert response.headers['content-language'] == 'en'
    assert response.headers['cache-control'] == 'no-store'
    outside = client.get(BASE + '?page=99').json()
    assert outside['items'] == [] and outside['totalElements'] == 3
    path = BASE + '/' + ids[0]
    headers = {'X-CSRF-Token': logged['csrfToken']}
    first = client.patch(path, json={'read': True}, headers=headers)
    assert first.status_code == 200, first.text
    auth_runtime.clock.advance(seconds=3)
    assert client.patch(path, json={'read': True}, headers=headers).json() == first.json()
    assert client.get(BASE + '?unreadOnly=true').json()['totalElements'] == 2
    for nid in (expired, str(uuid4())):
        assert_error(client.patch(BASE + '/' + nid, json={'read': True}, headers=headers),
                     404, 'NOTIFICATION_NOT_FOUND')
    login(client, 'ADMIN')
    assert client.get(BASE).json()['totalElements'] == 0
    assert_error(client.patch(path, json={'read': True}, headers={
        'X-CSRF-Token': login(client, 'ADMIN')['csrfToken'],
    }), 404, 'NOTIFICATION_NOT_FOUND')


@pytest.mark.parametrize('query', ['page=-1', 'size=0', 'size=101', 'unreadOnly=bad', 'userId=x'])
def test_invalid_query(client, query):
    login(client)
    assert_error(client.get(BASE + '?' + query), 400, 'VALIDATION_ERROR')


@pytest.mark.parametrize('body', [{}, {'read': False}, {'read': None}, {'read': 1},
                                  {'read': 'true'}, {'read': True, 'extra': 1}])
def test_invalid_read(client, auth_runtime, body):
    logged = login(client)
    nid = seed(auth_runtime, logged['user']['userId'])
    assert_error(client.patch(BASE + '/' + nid, json=body,
        headers={'X-CSRF-Token': logged['csrfToken']}), 400, 'VALIDATION_ERROR')
    assert client.get(BASE).json()['items'][0]['readAt'] is None


@pytest.mark.parametrize('method,path', [('GET', SETTINGS), ('PUT', SETTINGS),
    ('GET', BASE), ('PATCH', BASE + '/' + str(uuid4()))])
def test_auth_required(client, method, path):
    assert_error(client.request(method, path), 401, 'AUTH_REQUIRED')


@pytest.mark.parametrize('case,status,code', [
    ('csrf', 403, 'CSRF_INVALID'), ('origin', 403, 'ORIGIN_NOT_ALLOWED'),
    ('media', 415, 'UNSUPPORTED_MEDIA_TYPE'), ('json', 400, 'MALFORMED_JSON'),
])
@pytest.mark.parametrize('method', ['PUT', 'PATCH'])
def test_write_guards(client, method, case, status, code):
    logged = login(client)
    headers = {'X-CSRF-Token': logged['csrfToken'], 'Content-Type': 'application/json'}
    if case == 'csrf':
        headers.pop('X-CSRF-Token')
    elif case == 'origin':
        headers['Origin'] = 'https://untrusted.example.com'
    elif case == 'media':
        headers['Content-Type'] = 'text/plain'
    path = SETTINGS if method == 'PUT' else BASE + '/' + str(uuid4())
    assert_error(client.request(method, path, headers=headers, content='{'), status, code)


def test_concurrent_settings_and_read(client, auth_runtime):
    first = login(client)
    nid = seed(auth_runtime, first['user']['userId'])
    with TestClient(client.app, base_url='https://testserver') as second:
        other = login(second)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(c.put, SETTINGS, json=DEFAULTS,
                headers={'X-CSRF-Token': token}) for c, token in (
                    (client, first['csrfToken']), (second, other['csrfToken']))]
            assert all(f.result(timeout=15).status_code == 200 for f in futures)
            futures = [pool.submit(c.patch, BASE + '/' + nid, json={'read': True},
                headers={'X-CSRF-Token': token}) for c, token in (
                    (client, first['csrfToken']), (second, other['csrfToken']))]
            responses = [f.result(timeout=15) for f in futures]
            assert all(r.status_code == 200 for r in responses)
            assert responses[0].json()['readAt'] == responses[1].json()['readAt']


def test_openapi(client):
    paths = client.get('/openapi.json').json()['paths']
    for path, method in [(SETTINGS, 'get'), (SETTINGS, 'put'), (BASE, 'get'),
                         (BASE + '/{notificationId}', 'patch')]:
        operation = paths[path][method]
        assert '501' not in operation['responses']
        assert '200' in operation['responses']
        assert any(p['name'] == 'KAIFIND_SESSION' for p in operation['parameters'])


@pytest.mark.parametrize('kind,ko,en,path', [
    ('MATCH_CANDIDATE', '분실 신고와 일치할 수 있는 습득물이 등록되었습니다.',
     'A found item may match your lost report.', '/lost-reports'),
    ('ITEM_COLLECTED', '등록한 습득물의 수거가 완료되었습니다.',
     'Your found item has been collected.', '/found-items'),
    ('ITEM_EXPIRED', '등록한 습득물의 보관 기간이 만료되었습니다.',
     'Your found item has expired.', '/found-items'),
    ('KEYWORD_MATCH', '구독한 키워드와 일치하는 습득물이 등록되었습니다.',
     'A found item matches your subscribed keyword.', '/found-items'),
])
def test_notification_types_and_safe_payload(client, auth_runtime, kind, ko, en, path):
    logged = login(client)
    nid = seed(auth_runtime, logged['user']['userId'], kind=kind)
    for lang, message in [('ko', ko), ('en', en), ('ja', ko)]:
        response = client.get(BASE, headers={'Accept-Language': lang})
        assert response.status_code == 200, response.text
        row = response.json()['items'][0]
        assert set(row) == {
            'notificationId', 'type', 'message', 'targetPath',
            'itemId', 'reportId', 'createdAt', 'readAt',
        }
        assert row['notificationId'] == nid
        assert row['type'] == kind
        assert row['message'] == message
        assert row['targetPath'] == path
        assert row['itemId'] is None and row['reportId'] is None
        assert row['readAt'] is None

    # GET must not mark a notification read or enqueue email delivery.
    with auth_runtime.sync_engine.connect() as db:
        assert db.execute(text('SELECT read_at FROM notifications WHERE id=:id'),
                          {'id': nid}).scalar_one() is None
        assert db.execute(text('SELECT count(*) FROM email_delivery_items')).scalar_one() == 0


@pytest.mark.parametrize('method,path', [
    ('GET', SETTINGS), ('PUT', SETTINGS), ('GET', BASE),
    ('PATCH', BASE + '/' + str(uuid4())),
])
def test_expired_session(client, auth_runtime, method, path):
    login(client)
    auth_runtime.clock.advance(minutes=31)
    response = client.request(method, path, headers={'Accept-Language': 'en'})
    assert_error(response, 401, 'SESSION_EXPIRED')
    assert response.headers['content-language'] == 'en'
    assert not client.cookies.get('KAIFIND_SESSION')


def test_unread_empty_page_and_email_opt_out(client, auth_runtime):
    logged = login(client)
    seed(auth_runtime, logged['user']['userId'], read=True)
    headers = {'X-CSRF-Token': logged['csrfToken']}
    disabled = dict.fromkeys(DEFAULTS, False)
    assert client.put(SETTINGS, json=disabled, headers=headers).status_code == 200
    assert client.get(BASE).json()['totalElements'] == 1
    assert client.get(BASE + '?unreadOnly=true').json() == {
        'items': [], 'page': 0, 'size': 20, 'totalElements': 0, 'totalPages': 0,
    }


def test_failed_writes_preserve_existing_data(client, auth_runtime):
    logged = login(client)
    headers = {'X-CSRF-Token': logged['csrfToken']}
    disabled = dict.fromkeys(DEFAULTS, False)
    assert client.put(SETTINGS, json=disabled, headers=headers).status_code == 200
    nid = seed(auth_runtime, logged['user']['userId'])

    assert_error(client.put(SETTINGS, json=DEFAULTS), 403, 'CSRF_INVALID')
    assert_error(client.put(SETTINGS, json={**DEFAULTS, 'matchEmail': 'true'}, headers=headers),
                 400, 'VALIDATION_ERROR')
    assert client.get(SETTINGS).json() == disabled
    assert_error(client.patch(BASE + '/' + nid, json={'read': True}), 403, 'CSRF_INVALID')
    assert client.get(BASE).json()['items'][0]['readAt'] is None
    assert_error(client.patch(BASE + '/invalid-uuid', json={'read': True}, headers=headers),
                 400, 'VALIDATION_ERROR')
