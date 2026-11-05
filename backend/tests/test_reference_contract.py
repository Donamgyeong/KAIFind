"""Public reference acceptance tests on isolated PostgreSQL."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from main import app as full_app
from test_admin_contract import create_refs, item, login


BASE = '/api/v1'


@pytest.fixture
def client(auth_runtime):
    app = FastAPI()
    app.state.auth_runtime = auth_runtime
    app.state.reference_session_factory = auth_runtime.factory
    app.router.routes.extend(full_app.routes)
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('TRUNCATE buildings, categories, audit_logs CASCADE'))
    with TestClient(app, base_url='https://testserver') as client:
        yield client


def history(rt, item_id, user, buildings):
    with rt.sync_engine.begin() as db:
        for revision, building in enumerate(buildings, 1):
            db.execute(text('''INSERT INTO drop_off_versions
                (id,item_id,revision_no,mode,building_id,spot_description,changed_by_user_id)
                VALUES (:id,:item,:revision,:mode,:building,:spot,:user)'''),
                dict(id=str(uuid4()), item=item_id, revision=revision,
                     mode='DROP_OFF' if building else 'KEPT_BY_FINDER',
                     building=building, spot='보관 장소' if building else None, user=user))


def test_empty_validation_and_public_access(client, auth_runtime):
    for path in ('/buildings', '/categories'):
        assert client.get(BASE + path).json() == {'items': []}
        client.cookies.set('KAIFIND_SESSION', 'unknown')
        assert client.get(BASE + path).status_code == 200
        response = client.get(BASE + path + '?unknown=true', headers={'Accept-Language': 'en'})
        assert response.status_code == 400
        assert response.json()['code'] == 'VALIDATION_ERROR'
        assert response.json()['fieldErrors'][0]['field'] == 'unknown'
        assert response.headers['content-language'] == 'en'
        assert response.headers['cache-control'] == 'no-store'
    response = client.get(BASE + '/buildings?includePostedCount=invalid')
    assert response.status_code == 400
    assert response.json()['fieldErrors'][0]['field'] == 'includePostedCount'


def test_lists_admin_changes_and_counts(client, auth_runtime):
    user, headers = login(client)
    a, category = create_refs(client, headers)
    b = client.post(BASE + '/admin/buildings', headers=headers,
        json={'code': 'E4', 'nameKo': '다른 건물', 'nameEn': 'Other'}).json()['buildingId']
    zero = client.post(BASE + '/admin/buildings', headers=headers,
        json={'code': 'E5', 'nameKo': '빈 건물', 'nameEn': 'Empty'}).json()['buildingId']

    # Found building A, current drop-off B; earlier revisions must not count.
    history(auth_runtime, item(auth_runtime, user, a, category), user, [a, b, b])
    history(auth_runtime, item(auth_runtime, user, a, category), user, [a, None])
    history(auth_runtime, item(auth_runtime, user, a, category), user, [None, a])
    for changes in (
        {'hidden': True}, {'deleted': auth_runtime.clock()},
        {'status': 'COLLECTED', 'closed': auth_runtime.clock()},
        {'status': 'EXPIRED', 'closed': auth_runtime.clock()},
    ):
        history(auth_runtime, item(auth_runtime, user, a, category, **changes), user, [a])
    item(auth_runtime, user, a, category)  # No drop-off history.

    for key in ('admin-01', 'student-01'):
        login(client, key)
        response = client.get(BASE + '/buildings?includePostedCount=true')
        assert response.status_code == 200, response.text
        assert {r['buildingId']: r['postedCount'] for r in response.json()['items']} == {
            a: 1, b: 1, zero: 0,
        }
    client.cookies.clear()
    assert client.get(BASE + '/buildings?includePostedCount=true').json() == response.json()
    for suffix in ('', '?includePostedCount=false'):
        assert all('postedCount' not in r for r in client.get(BASE + '/buildings' + suffix).json()['items'])
    categories = client.get(BASE + '/categories').json()['items']
    assert categories == [dict(categoryId=category, nameKo='지갑', nameEn='Wallet', active=True, sensitive=True)]

    _, headers = login(client)
    assert client.patch(BASE + f'/admin/buildings/{a}', headers=headers,
                        json={'nameEn': 'Renamed'}).status_code == 200
    assert next(r for r in client.get(BASE + '/buildings').json()['items'] if r['buildingId'] == a)['nameEn'] == 'Renamed'
    for kind, key in (('buildings', a), ('categories', category)):
        assert client.patch(BASE + f'/admin/{kind}/{key}', headers=headers,
                            json={'active': False}).status_code == 200
    assert len(client.get(BASE + '/buildings').json()['items']) == 2
    assert client.get(BASE + '/categories').json() == {'items': []}


def test_database_failure_is_localized_and_sanitized(client):
    def failing_factory():
        raise RuntimeError('secret connection details')

    client.app.state.reference_session_factory = failing_factory
    response = client.get(BASE + '/buildings', headers={'Accept-Language': 'en'})
    assert response.status_code == 500
    assert response.json() == dict(code='INTERNAL_SERVER_ERROR',
        message='An internal server error occurred.', fieldErrors=[])
    assert response.headers['content-language'] == 'en'
    assert response.headers['cache-control'] == 'no-store'


def test_order_and_expired_cookie(client, auth_runtime):
    _, headers = login(client)
    keys = []
    for code in ('E1', 'E2', 'E3'):
        response = client.post(BASE + '/admin/buildings', headers=headers,
            json={'code': code, 'nameKo': code, 'nameEn': code})
        assert response.status_code == 201
        keys.append(response.json()['buildingId'])
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('UPDATE buildings SET created_at=:now'), {'now': auth_runtime.clock()})
        db.execute(text('UPDATE buildings SET created_at=:older WHERE id=:id'),
                   {'older': auth_runtime.clock().replace(year=2025), 'id': keys[0]})
    auth_runtime.clock.advance(minutes=31)
    rows = client.get(BASE + '/buildings').json()['items']
    assert [r['buildingId'] for r in rows] == sorted(keys[1:], reverse=True) + [keys[0]]
    assert client.get(BASE + '/categories').status_code == 200
