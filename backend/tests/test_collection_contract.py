"""Collection contracts and atomicity on disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from test_admin_contract import client, create_refs, error, item, login
from service import collections as collection_service


@pytest.fixture
def setup(client, auth_runtime):
    admin, headers = login(client)
    building, category = create_refs(client, headers)
    finder, headers = login(client, 'student-01')
    key = item(auth_runtime, finder, building, category)
    return key, finder, building, category, headers


def path(key):
    return f'/api/v1/found-items/{key}/collection'


def collect(client, key, headers):
    return client.post(path(key), headers=headers, json={'confirmedOwnership': True})


def test_lifecycle(client, auth_runtime, setup):
    key, finder, _, _, headers = setup
    error(client.get(path(key)), 404, 'COLLECTION_NOT_FOUND')
    response = collect(client, key, headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert set(data) == {'collectionId', 'itemId', 'collectorId', 'collectedAt', 'status'}
    assert data['collectorId'] == finder
    assert data['collectedAt'].endswith('+09:00')
    assert client.get(path(key)).json() == data
    error(collect(client, key, headers), 409, 'ALREADY_COLLECTED')
    cancelled = client.delete(path(key), headers=headers)
    assert cancelled.status_code == 204 and cancelled.content == b''
    error(client.delete(path(key), headers=headers), 409, 'ITEM_NOT_COLLECTED')
    response = collect(client, key, headers)
    assert response.status_code == 201, response.text
    assert response.json()['collectionId'] != data['collectionId']
    with auth_runtime.sync_engine.connect() as db:
        assert db.execute(text('SELECT count(*) FROM collections WHERE item_id=:id'), {'id': key}).scalar_one() == 2
        assert db.execute(text("SELECT count(*) FROM outbox_events WHERE event_type='COLLECTION_NOTIFICATION' AND payload->>'itemId'=:id"), {'id': key}).scalar_one() == 2


@pytest.mark.parametrize('body', [{}, {'confirmedOwnership': False}, {'confirmedOwnership': None},
    {'confirmedOwnership': 1}, {'confirmedOwnership': 'true'},
    {'confirmedOwnership': True, 'collectorId': str(uuid4())}])
def test_confirmation(client, setup, body):
    key, _, _, _, headers = setup
    error(client.post(path(key), headers=headers, json=body), 400, 'VALIDATION_ERROR')


def test_security_and_visibility(client, auth_runtime, setup):
    key, _, _, _, headers = setup
    error(collect(client, key, {}), 403, 'CSRF_INVALID')
    assert collect(client, key, headers).status_code == 201
    _, other_headers = login(client, 'faculty-01')
    error(client.get(path(key)), 403, 'FORBIDDEN')
    error(client.delete(path(key), headers=other_headers), 403, 'FORBIDDEN')
    _, admin_headers = login(client)
    assert client.get(path(key)).status_code == 200
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('UPDATE found_items SET hidden=true WHERE id=:id'), {'id': key})
    assert client.delete(path(key), headers=admin_headers).status_code == 204
    error(collect(client, key, admin_headers), 404, 'NOT_FOUND')
    with TestClient(client.app, base_url='https://testserver') as anonymous:
        error(anonymous.get(path(key)), 401, 'AUTH_REQUIRED')


def test_concurrent_collection(client, setup):
    key, _, _, _, headers = setup
    with TestClient(client.app, base_url='https://testserver') as other:
        _, other_headers = login(other, 'faculty-01')
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(collect, c, key, h) for c, h in
                       [(client, headers), (other, other_headers)]]
            results = [future.result() for future in futures]
    assert sorted(r.status_code for r in results) == [201, 409]


def test_atomic_audit_failure(client, auth_runtime, setup, monkeypatch):
    key, _, _, _, headers = setup
    def fail(*args, **kwargs):
        raise RuntimeError('audit failure')
    monkeypatch.setattr(collection_service, 'append_audit', fail)
    error(collect(client, key, headers), 500, 'INTERNAL_SERVER_ERROR')
    with auth_runtime.sync_engine.connect() as db:
        assert db.execute(text('SELECT status FROM found_items WHERE id=:id'), {'id': key}).scalar_one() == 'POSTED'
        assert db.execute(text('SELECT count(*) FROM collections WHERE item_id=:id'), {'id': key}).scalar_one() == 0


def test_matching_pending_rolls_back(client, auth_runtime, setup):
    key, finder, _, category, headers = setup
    report_id = str(uuid4())
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('''INSERT INTO lost_reports
            (id,owner_id,category_id,description,lost_date_from,lost_date_to,expires_at)
            VALUES (:id,:owner,:category,'description',:date,:date,:expires)'''),
            dict(id=report_id, owner=finder, category=category, date=auth_runtime.clock().date(),
                 expires=auth_runtime.clock() + timedelta(days=30)))
        db.execute(text('INSERT INTO lost_report_private_details (report_id,details) VALUES (:id, :details)'),
                   dict(id=report_id, details='private'))
    error(collect(client, key, headers), 409, 'MATCHING_PENDING')
    with auth_runtime.sync_engine.connect() as db:
        assert db.execute(text('SELECT status FROM found_items WHERE id=:id'), {'id': key}).scalar_one() == 'POSTED'
        assert db.execute(text('SELECT count(*) FROM collections WHERE item_id=:id'), {'id': key}).scalar_one() == 0


def test_message_deletion_and_restriction(client, auth_runtime, setup):
    key, finder, _, _, _ = setup
    collector, headers = login(client, 'faculty-01')
    conversation = client.post('/api/v1/conversations', headers=headers, json={'itemId': key})
    assert conversation.status_code == 201
    cid = conversation.json()['conversationId']
    assert client.post(f'/api/v1/conversations/{cid}/messages', headers=headers,
                       json={'content': 'private message'}).status_code == 201
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('''INSERT INTO collection_restrictions
            (user_id,restricted,updated_by_user_id) VALUES (:id,true,:finder)'''),
            dict(id=collector, finder=finder))
    error(collect(client, key, headers), 403, 'COLLECTION_RESTRICTED')
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('UPDATE collection_restrictions SET restricted=false WHERE user_id=:id'), {'id': collector})
    assert collect(client, key, headers).status_code == 201
    with auth_runtime.sync_engine.connect() as db:
        assert db.execute(text('SELECT count(*) FROM conversations WHERE id=:id'), {'id': cid}).scalar_one() == 0
        assert db.execute(text('SELECT count(*) FROM messages WHERE conversation_id=:id'), {'id': cid}).scalar_one() == 0
    assert client.delete(path(key), headers=headers).status_code == 204
    with auth_runtime.sync_engine.connect() as db:
        posted, expires, closed, purge = db.execute(text('''SELECT posted_at,expires_at,closed_at,purge_after
            FROM found_items WHERE id=:id'''), {'id': key}).one()
        assert posted == auth_runtime.clock() and expires == posted + timedelta(days=30)
        assert closed is purge is None
