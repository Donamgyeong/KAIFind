"""Dispute submission, history and review contracts on disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from test_admin_contract import client, create_refs, error, item, login


@pytest.fixture
def setup(client, auth_runtime):
    admin, headers = login(client)
    building, category = create_refs(client, headers)
    finder, headers = login(client, 'student-01')
    key = item(
        auth_runtime, finder, building, category,
        status='COLLECTED', closed=auth_runtime.clock(),
    )
    collection = add_collection(auth_runtime, key, finder, admin)
    return key, collection, finder, admin, headers


def add_collection(rt, key, finder, collector):
    collection = str(uuid4())
    with rt.sync_engine.begin() as db:
        db.execute(text('''INSERT INTO collections
            (id,item_id,finder_id,collector_id,collected_at,purge_after)
            VALUES (:id,:item,:finder,:collector,:now,:purge)'''),
            dict(id=collection, item=key, finder=finder, collector=collector,
                 now=rt.clock(), purge=rt.clock() + timedelta(days=365)))
    return collection


def path(key):
    return f'/api/v1/found-items/{key}/disputes'


def submit(client, key, headers, reason='  잘못된 수거입니다.  '):
    return client.post(path(key), headers=headers, json={'reason': reason})


def test_creation_review_and_retention(client, auth_runtime, setup):
    key, collection, finder, collector, headers = setup
    response = submit(client, key, headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert set(data) == {'disputeId', 'itemId', 'collectionId', 'reason', 'status',
                         'decision', 'createdAt', 'resolvedAt'}
    assert data['collectionId'] == collection and data['itemId'] == key
    assert data['reason'] == '잘못된 수거입니다.'
    assert data['status'] == 'OPEN' and data['decision'] is data['resolvedAt'] is None
    assert data['createdAt'].endswith('+09:00')
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['content-language'] == 'ko'
    assert client.get(path(key)).json()['items'] == [data]
    error(submit(client, key, headers), 409, 'OPEN_DISPUTE_EXISTS')
    with auth_runtime.sync_engine.connect() as db:
        assert db.execute(text('''SELECT d.purge_after=c.purge_after FROM disputes d
            JOIN collections c ON c.id=d.collection_id WHERE d.id=:id'''),
            {'id': data['disputeId']}).scalar_one()
        assert db.execute(text('SELECT status FROM found_items WHERE id=:id'), {'id': key}).scalar_one() == 'COLLECTED'
        assert db.execute(text('SELECT count(*) FROM collection_restrictions')).scalar_one() == 0

    _, admin_headers = login(client)
    assert client.get(path(key)).status_code == 200
    admin_path = '/api/v1/admin/disputes/' + data['disputeId']
    assert client.get('/api/v1/admin/disputes').json()['totalElements'] == 1
    assert client.get(admin_path).json()['finderId'] == finder
    reviewed = client.post(admin_path + '/review', headers=admin_headers,
                          json={'decision': 'UPHELD', 'blockCollector': True})
    assert reviewed.status_code == 200, reviewed.text
    error(client.post(admin_path + '/review', headers=admin_headers,
                      json={'decision': 'DISMISSED', 'blockCollector': False}),
          409, 'DISPUTE_ALREADY_RESOLVED')
    with auth_runtime.sync_engine.connect() as db:
        assert db.execute(text('SELECT restricted FROM collection_restrictions WHERE user_id=:id'),
                          {'id': collector}).scalar_one()
    _, headers = login(client, 'student-01')
    listed = client.get(path(key)).json()['items'][0]
    assert listed['decision'] == 'UPHELD' and listed['resolvedAt'].endswith('+09:00')
    # A resolved dispute does not prevent a new submission for this collection.
    assert submit(client, key, headers).status_code == 201


@pytest.mark.parametrize('body', [{}, {'reason': None}, {'reason': 1}, {'reason': True},
    {'reason': ''}, {'reason': ' \n\t '}, {'reason': 'x' * 1001},
    {'reason': 'valid', 'collectionId': str(uuid4())}])
def test_invalid_body(client, setup, body):
    key, _, _, _, headers = setup
    error(client.post(path(key), headers=headers, json=body), 400, 'VALIDATION_ERROR')
    assert client.get(path(key)).json()['totalElements'] == 0


def test_access_and_hidden_deleted_missing(client, auth_runtime, setup):
    key, _, _, _, headers = setup
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('UPDATE found_items SET hidden=true WHERE id=:id'), {'id': key})
    assert submit(client, key, headers).status_code == 201
    assert client.get(path(key)).status_code == 200
    _, outsider_headers = login(client, 'faculty-01')
    error(submit(client, key, outsider_headers), 403, 'FINDER_ONLY')
    error(client.get(path(key)), 403, 'FORBIDDEN')
    _, admin_headers = login(client)
    error(submit(client, key, admin_headers), 403, 'FINDER_ONLY')
    assert client.get(path(key)).status_code == 200
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('UPDATE found_items SET deleted_at=:now WHERE id=:id'),
                   {'id': key, 'now': auth_runtime.clock()})
    error(client.get(path(key)), 404, 'NOT_FOUND')
    error(submit(client, key, admin_headers), 404, 'NOT_FOUND')
    error(client.get(path(str(uuid4()))), 404, 'NOT_FOUND')
    error(submit(client, str(uuid4()), admin_headers), 404, 'NOT_FOUND')


@pytest.mark.parametrize('change', ['POSTED', 'EXPIRED', 'missing_collection'])
def test_not_collected(client, auth_runtime, setup, change):
    key, collection, _, _, headers = setup
    with auth_runtime.sync_engine.begin() as db:
        if change == 'missing_collection':
            db.execute(text('DELETE FROM collections WHERE id=:id'), {'id': collection})
        else:
            db.execute(text('UPDATE found_items SET status=:status, closed_at=:closed WHERE id=:id'),
                       {'id': key, 'status': change,
                        'closed': None if change == 'POSTED' else auth_runtime.clock()})
    error(submit(client, key, headers), 409, 'ITEM_NOT_COLLECTED')


def test_recollection_history_and_pagination(client, auth_runtime, setup):
    key, old, finder, collector, headers = setup
    first = submit(client, key, headers).json()
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('UPDATE collections SET undone_at=:now, undone_by_user_id=:user WHERE id=:id'),
                   {'id': old, 'user': finder, 'now': auth_runtime.clock()})
    new = add_collection(auth_runtime, key, finder, collector)
    second = submit(client, key, headers, 'x' * 1000)
    assert second.status_code == 201, second.text
    second = second.json()
    assert second['collectionId'] == new
    # Equal timestamps must use descending UUID order.
    expected = sorted([first, second], key=lambda row: row['disputeId'], reverse=True)
    assert client.get(path(key)).json()['items'] == expected
    page = client.get(path(key) + '?size=1&page=1').json()
    assert page['items'] == expected[1:]
    assert page['totalElements'] == page['totalPages'] == 2
    assert client.get(path(key) + '?page=2&size=1').json()['items'] == []


@pytest.mark.parametrize('query', ['page=-1', 'size=0', 'size=101', 'unknown=1', 'page=null'])
def test_invalid_query(client, setup, query):
    key, *_ = setup
    error(client.get(path(key) + '?' + query), 400, 'VALIDATION_ERROR')


def test_security_and_openapi(client, setup):
    key, _, _, _, headers = setup
    error(submit(client, key, {}), 403, 'CSRF_INVALID')
    for extra, content, status, code in [
        ({'Origin': 'https://evil.example'}, '{}', 403, 'ORIGIN_NOT_ALLOWED'),
        ({'Content-Type': 'text/plain'}, '{}', 415, 'UNSUPPORTED_MEDIA_TYPE'),
        ({'Content-Type': 'application/json'}, '{', 400, 'MALFORMED_JSON'),
    ]:
        response = client.post(path(key), headers={**headers, **extra, 'Accept-Language': 'en'}, content=content)
        error(response, status, code)
        assert response.headers['content-language'] == 'en'
    spec = client.get('/openapi.json').json()['paths']['/api/v1/found-items/{itemId}/disputes']
    assert '201' in spec['post']['responses'] and '501' not in spec['post']['responses']
    assert {'page', 'size', 'KAIFIND_SESSION'} <= {p['name'] for p in spec['get']['parameters']}
    client.cookies.clear()
    error(client.get(path(key)), 401, 'AUTH_REQUIRED')
    error(submit(client, key, headers), 401, 'AUTH_REQUIRED')


def test_concurrent_submission(client, setup):
    key, *_ = setup
    with TestClient(client.app, base_url='https://testserver') as second:
        _, first_headers = login(client, 'student-01')
        _, second_headers = login(second, 'student-01')
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(submit, c, key, h) for c, h in (
                (client, first_headers), (second, second_headers),
            )]
            responses = [f.result(timeout=15) for f in futures]
    assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]
    error(next(r for r in responses if r.status_code == 409), 409, 'OPEN_DISPUTE_EXISTS')
    assert client.get(path(key)).json()['totalElements'] == 1


def test_cancellation_transaction_race(client, auth_runtime, setup):
    key, collection, finder, _, headers = setup
    started = Event()

    def send():
        started.set()
        return submit(client, key, headers)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with auth_runtime.sync_engine.begin() as db:
            db.execute(text('SELECT id FROM found_items WHERE id=:id FOR UPDATE'), {'id': key})
            future = pool.submit(send)
            assert started.wait(5)
            db.execute(text("UPDATE found_items SET status='POSTED', closed_at=NULL WHERE id=:id"), {'id': key})
            db.execute(text('UPDATE collections SET undone_at=:now, undone_by_user_id=:user WHERE id=:id'),
                       {'id': collection, 'now': auth_runtime.clock(), 'user': finder})
        error(future.result(timeout=15), 409, 'ITEM_NOT_COLLECTED')
    assert client.get(path(key)).json()['totalElements'] == 0
