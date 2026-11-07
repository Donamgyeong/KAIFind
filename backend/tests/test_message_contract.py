"""Messaging HTTP contracts and races on disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from test_admin_contract import client, create_refs, error, item, login


BASE = '/api/v1/conversations'


@pytest.fixture
def setup(client, auth_runtime):
    finder, headers = login(client)
    building, category = create_refs(client, headers)
    item_id = item(auth_runtime, finder, building, category)
    return finder, item_id


def create(client, headers, item_id):
    return client.post(BASE, headers=headers, json={'itemId': item_id})


def test_creation_reuse_send_and_access(client, auth_runtime, setup):
    finder, item_id = setup
    _, finder_headers = login(client)
    error(create(client, finder_headers, item_id), 409, 'SELF_CONVERSATION')
    member, headers = login(client, 'student-01')
    response = create(client, headers, item_id)
    assert response.status_code == 201, response.text
    conversation = response.json()
    assert conversation['finderId'] == finder
    assert conversation['memberId'] == member
    assert conversation['createdAt'].endswith('+09:00')
    assert create(client, headers, item_id).json() == conversation
    assert create(client, headers, item_id).status_code == 200
    path = BASE + '/' + conversation['conversationId'] + '/messages'
    auth_runtime.clock.advance(seconds=1)
    response = client.post(path, headers=headers, json={'content': '  안녕하세요\n물품 문의입니다.  '})
    assert response.status_code == 201, response.text
    assert response.json()['content'] == '안녕하세요\n물품 문의입니다.'
    assert response.json()['senderId'] == member
    assert client.get(BASE).json()['items'][0]['updatedAt'] == response.json()['createdAt']
    assert client.get(path).json()['items'] == [response.json()]

    _, finder_headers = login(client)
    assert client.get(path).status_code == 200
    assert client.post(path, headers=finder_headers, json={'content': '답변입니다.'}).status_code == 201
    outsider, other_headers = login(client, 'faculty-01')
    error(client.get(path), 404, 'CONVERSATION_NOT_FOUND')
    assert client.get(BASE).json()['totalElements'] == 0
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text("UPDATE users SET role='ADMIN' WHERE id=:id"), {'id': outsider})
    error(client.get(path), 404, 'CONVERSATION_NOT_FOUND')
    error(client.post(path, headers=other_headers, json={'content': 'no'}), 404, 'CONVERSATION_NOT_FOUND')
    assert create(client, other_headers, item_id).json()['conversationId'] != conversation['conversationId']


@pytest.mark.parametrize('content', ['', '   ', None, 1, True, 'x' * 2001])
def test_invalid_content(client, setup, content):
    _, item_id = setup
    _, headers = login(client, 'student-01')
    cid = create(client, headers, item_id).json()['conversationId']
    path = f'{BASE}/{cid}/messages'
    error(client.post(path, headers=headers, json={'content': content}), 400, 'VALIDATION_ERROR')
    assert client.get(path).json()['totalElements'] == 0


@pytest.mark.parametrize('content', ['a@example.com', '010-1234-5678', '+82 10 1234 5678'])
def test_contacts_allowed_and_guards(client, setup, content):
    _, item_id = setup
    _, headers = login(client, 'student-01')
    cid = create(client, headers, item_id).json()['conversationId']
    path = f'{BASE}/{cid}/messages'
    response = client.post(path, headers=headers, json={'content': content})
    assert response.status_code == 201, response.text
    assert response.json()['content'] == content
    assert client.get(path).json()['items'] == [response.json()]
    error(client.post(path, json={'content': 'hello'}), 403, 'CSRF_INVALID')
    error(client.get(path + '?unknown=1'), 400, 'VALIDATION_ERROR')
    error(client.get(BASE + '?size=101'), 400, 'VALIDATION_ERROR')
    client.cookies.clear()
    error(client.get(path), 401, 'AUTH_REQUIRED')


def test_concurrent_creation(client, auth_runtime, setup):
    _, item_id = setup
    # Separate login sessions for the same member avoid the auth session lock serializing the race.
    with TestClient(client.app, base_url='https://testserver') as second:
        _, first_headers = login(client, 'student-01')
        _, second_headers = login(second, 'student-01')
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(create, c, h, item_id) for c, h in (
                (client, first_headers), (second, second_headers),
            )]
            responses = [future.result(timeout=15) for future in futures]
    assert sorted(r.status_code for r in responses) == [200, 201], [r.text for r in responses]
    assert len({r.json()['conversationId'] for r in responses}) == 1
    with auth_runtime.sync_engine.connect() as db:
        assert db.execute(text('SELECT count(*) FROM conversations WHERE item_id=:id'), {'id': item_id}).scalar_one() == 1


@pytest.mark.parametrize('change', ['EXPIRED', 'COLLECTED', 'deleted'])
def test_closure_send_race(client, auth_runtime, setup, change):
    _, item_id = setup
    _, headers = login(client, 'student-01')
    cid = create(client, headers, item_id).json()['conversationId']
    path = f'{BASE}/{cid}/messages'
    assert client.post(path, headers=headers, json={'content': 'hello'}).status_code == 201
    started = Event()

    def send():
        started.set()
        return client.post(path, headers=headers, json={'content': 'racing'})

    with ThreadPoolExecutor(max_workers=1) as pool:
        with auth_runtime.sync_engine.begin() as db:
            db.execute(text('SELECT id FROM found_items WHERE id=:id FOR UPDATE'), {'id': item_id})
            future = pool.submit(send)
            assert started.wait(5)
            if change == 'deleted':
                db.execute(text('UPDATE found_items SET deleted_at=:now WHERE id=:id'),
                           {'now': auth_runtime.clock(), 'id': item_id})
            else:
                db.execute(text('UPDATE found_items SET status=:status, closed_at=:now WHERE id=:id'),
                           {'status': change, 'now': auth_runtime.clock(), 'id': item_id})
        error(future.result(timeout=15), 404, 'CONVERSATION_NOT_FOUND')
    assert client.get(BASE).json()['totalElements'] == 0
    error(client.get(path), 404, 'CONVERSATION_NOT_FOUND')
    with auth_runtime.sync_engine.connect() as db:
        assert db.execute(text('SELECT count(*) FROM messages WHERE conversation_id=:id'), {'id': cid}).scalar_one() == 0


def test_hidden_closed_missing_and_pagination(client, auth_runtime, setup):
    _, item_id = setup
    _, headers = login(client, 'student-01')
    cid = create(client, headers, item_id).json()['conversationId']
    path = f'{BASE}/{cid}/messages'
    for index in range(3):
        auth_runtime.clock.advance(seconds=1)
        assert client.post(path, headers=headers, json={'content': str(index)}).status_code == 201
    page = client.get(path + '?page=1&size=2').json()
    assert [m['content'] for m in page['items']] == ['2']
    assert page['totalElements'] == 3 and page['totalPages'] == 2
    assert client.get(BASE + '?itemId=' + str(uuid4())).json()['items'] == []
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('UPDATE found_items SET hidden=true WHERE id=:id'), {'id': item_id})
    error(create(client, headers, item_id), 404, 'NOT_FOUND')
    assert client.get(path).status_code == 200
    assert client.post(path, headers=headers, json={'content': 'hidden reply'}).status_code == 201
    error(create(client, headers, str(uuid4())), 404, 'NOT_FOUND')


@pytest.mark.parametrize('changes,code,status', [
    ({'status': 'EXPIRED'}, 'ITEM_CLOSED', 409),
    ({'status': 'COLLECTED'}, 'ITEM_CLOSED', 409),
    ({'hidden': True}, 'NOT_FOUND', 404),
    ({'deleted': True}, 'NOT_FOUND', 404),
])
def test_unavailable_item(client, auth_runtime, setup, changes, code, status):
    finder, _ = setup
    _, admin_headers = login(client)
    # Reuse existing references rather than creating duplicate names.
    with auth_runtime.sync_engine.connect() as db:
        building = str(db.execute(text('SELECT id FROM buildings LIMIT 1')).scalar_one())
        category = str(db.execute(text('SELECT id FROM categories LIMIT 1')).scalar_one())
    if 'status' in changes:
        changes['closed'] = auth_runtime.clock()
    if 'deleted' in changes:
        changes['deleted'] = auth_runtime.clock()
    item_id = item(auth_runtime, finder, building, category, **changes)
    _, headers = login(client, 'student-01')
    error(create(client, headers, item_id), status, code)


@pytest.mark.parametrize('body', [{}, {'itemId': None}, {'itemId': 'bad'}, {'itemId': 1},
                                 {'itemId': str(uuid4()), 'memberId': str(uuid4())}])
def test_creation_input(client, setup, body):
    _, headers = login(client, 'student-01')
    error(client.post(BASE, headers=headers, json=body), 400, 'VALIDATION_ERROR')


def test_write_security_and_openapi(client, setup):
    _, item_id = setup
    _, headers = login(client, 'student-01')
    for extra, content, status, code in [
        ({'Origin': 'https://evil.example'}, '{}', 403, 'ORIGIN_NOT_ALLOWED'),
        ({'Content-Type': 'text/plain'}, '{}', 415, 'UNSUPPORTED_MEDIA_TYPE'),
        ({'Content-Type': 'application/json'}, '{', 400, 'MALFORMED_JSON'),
    ]:
        response = client.post(BASE, headers={**headers, **extra, 'Accept-Language': 'en'}, content=content)
        error(response, status, code)
        assert response.headers['content-language'] == 'en'
    cid = create(client, headers, item_id).json()['conversationId']
    path = f'{BASE}/{cid}/messages'
    response = client.post(path, headers=headers, json={'content': 'x' * 2000})
    assert response.status_code == 201
    error(client.post(path, headers=headers, json={'content': 'hello', 'senderId': str(uuid4())}),
          400, 'VALIDATION_ERROR')
    spec = client.get('/openapi.json').json()
    assert {'200', '201'} <= set(spec['paths'][BASE]['post']['responses'])
    assert {p['name'] for p in spec['paths'][BASE]['get']['parameters']} >= {'itemId', 'page', 'size'}
