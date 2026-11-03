"""Admin HTTP, transaction and concurrency acceptance tests on disposable PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from main import app as full_app
from model import AuditLog
from service import admin as admin_service

BASE = '/api/v1'


@pytest.fixture
def client(auth_runtime):
    # Full production route registration, with a disposable database and fixed clock.
    app = FastAPI()
    app.state.auth_runtime = auth_runtime
    for route in full_app.routes:
        app.router.routes.append(route)
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('TRUNCATE buildings, categories, audit_logs CASCADE'))
    with TestClient(app, base_url='https://testserver') as client:
        yield client


def login(client, key='admin-01'):
    csrf = client.get(BASE + '/auth/csrf').json()['csrfToken']
    response = client.post(BASE + '/auth/mock/login', json={'mockAccountId': key},
                           headers={'X-CSRF-Token': csrf})
    assert response.status_code == 200, response.text
    data = response.json()
    return data['user']['userId'], {'X-CSRF-Token': data['csrfToken']}


def error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()['code'] == code
    assert set(response.json()) == {'code', 'message', 'fieldErrors'}
    assert response.headers['cache-control'] == 'no-store'


def create_refs(client, headers):
    b = client.post(BASE + '/admin/buildings', headers=headers,
        json={'code': 'e3', 'nameKo': '전산학부', 'nameEn': 'Computing'})
    c = client.post(BASE + '/admin/categories', headers=headers,
        json={'nameKo': '지갑', 'nameEn': 'Wallet', 'sensitive': True})
    assert b.status_code == c.status_code == 201, (b.text, c.text)
    return b.json()['buildingId'], c.json()['categoryId']


def item(rt, finder, building, category, **changes):
    key = str(uuid4())
    data = dict(id=key, finder=finder, building=building, category=category,
        now=rt.clock(), expires=rt.clock() + timedelta(days=30), status='POSTED',
        closed=None, purge=None, hidden=False, deleted=None)
    data.update(changes)
    with rt.sync_engine.begin() as db:
        db.execute(text('''INSERT INTO found_items
            (id,finder_id,category_id,found_building_id,title,description,found_location_description,
             found_at,expires_at,status,closed_at,purge_after,hidden,deleted_at)
            VALUES (:id,:finder,:category,:building,'물품','설명','발견 장소',
                    :now,:expires,:status,:closed,:purge,:hidden,:deleted)'''), data)
    return key


def dispute(rt, finder, collector, item_id):
    collection_id, dispute_id = str(uuid4()), str(uuid4())
    with rt.sync_engine.begin() as db:
        db.execute(text('''INSERT INTO collections
            (id,item_id,finder_id,collector_id,collected_at,purge_after)
            VALUES (:id,:item,:finder,:collector,:now,:purge)'''),
            dict(id=collection_id, item=item_id, finder=finder, collector=collector,
                 now=rt.clock(), purge=rt.clock() + timedelta(days=365)))
        db.execute(text('''INSERT INTO disputes (id,collection_id,reason,status,purge_after)
            VALUES (:id,:collection,'잘못된 수거','OPEN',:purge)'''),
            dict(id=dispute_id, collection=collection_id, purge=rt.clock() + timedelta(days=365)))
    return collection_id, dispute_id


def test_admin_authentication_and_current_role(client):
    error(client.get(BASE + '/admin/users'), 401, 'AUTH_REQUIRED')
    login(client, 'student-01')
    error(client.get(BASE + '/admin/users'), 403, 'FORBIDDEN')


def test_role_changes_immediately_apply_and_survive_login(client):
    actor, headers = login(client)
    with TestClient(client.app, base_url='https://testserver') as member:
        member_id, _ = login(member, 'student-01')
        path = BASE + f'/admin/users/{member_id}/role'
        assert client.patch(path, headers=headers, json={'role': 'ADMIN'}).status_code == 200
        assert member.get(BASE + '/admin/users').status_code == 200
        assert client.patch(path, headers=headers, json={'role': 'MEMBER'}).status_code == 200
        error(member.get(BASE + '/admin/users'), 403, 'FORBIDDEN')
        login(member, 'student-01')
        error(member.get(BASE + '/admin/users'), 403, 'FORBIDDEN')
    error(client.patch(BASE + f'/admin/users/{actor}/role', headers=headers,
                       json={'role': 'MEMBER'}), 409, 'LAST_ADMIN')
    result = client.get(BASE + '/admin/users').json()
    assert all(set(row) == {'userId', 'name', 'affiliation', 'role', 'collectionRestricted'} for row in result['items'])
    assert client.get(BASE + '/admin/users?q=%').json()['totalElements'] == 0


@pytest.mark.parametrize('method,path,body', [
    ('POST', '/admin/buildings', {'code': 'E3', 'nameKo': '건물', 'nameEn': 'Building'}),
    ('PATCH', '/admin/buildings/' + str(uuid4()), {'active': False}),
    ('PUT', '/admin/users/' + str(uuid4()) + '/collection-restriction', {'restricted': False}),
])
def test_all_write_methods_enforce_csrf_origin_json(client, method, path, body):
    _, headers = login(client)
    error(client.request(method, BASE + path, json=body), 403, 'CSRF_INVALID')
    error(client.request(method, BASE + path, json=body, headers=dict(headers, Origin='https://evil.test')),
          403, 'ORIGIN_NOT_ALLOWED')
    error(client.request(method, BASE + path, content='{}', headers=dict(headers, **{'Content-Type': 'text/plain'})),
          415, 'UNSUPPORTED_MEDIA_TYPE')
    error(client.request(method, BASE + path, content='{', headers=dict(headers, **{'Content-Type': 'application/json'})),
          400, 'MALFORMED_JSON')


def test_reference_crud_validation_and_conflicts(client, auth_runtime):
    _, headers = login(client)
    building, category = create_refs(client, headers)
    error(client.post(BASE + '/admin/buildings', headers=headers,
        json={'code': ' E3 ', 'nameKo': '다른 이름', 'nameEn': 'Other'}), 409, 'BUILDING_CODE_EXISTS')
    error(client.post(BASE + '/admin/categories', headers=headers,
        json={'nameKo': '다른 이름', 'nameEn': ' wallet ', 'sensitive': False}), 409, 'CATEGORY_NAME_EXISTS')
    for resource, key in [('buildings', building), ('categories', category)]:
        path = BASE + f'/admin/{resource}/{key}'
        for payload in [{}, {'active': None}, {'active': 'false'}, {'unknown': True}]:
            error(client.patch(path, headers=headers, json=payload), 400, 'VALIDATION_ERROR')
        result = client.patch(path, headers=headers, json={'active': False, 'nameKo': '수정 이름'})
        assert result.status_code == 200, result.text
        assert result.json()['active'] is False
        assert client.get(BASE + f'/admin/{resource}?active=true').json()['totalElements'] == 0
        assert client.get(BASE + f'/admin/{resource}?active=false').json()['totalElements'] == 1
    error(client.get(BASE + '/admin/users?size=101'), 400, 'VALIDATION_ERROR')
    error(client.get(BASE + '/admin/users?page=-1'), 400, 'VALIDATION_ERROR')
    error(client.get(BASE + '/admin/users?role=ROOT'), 400, 'VALIDATION_ERROR')
    error(client.get(BASE + '/admin/users?unknown=true'), 400, 'VALIDATION_ERROR')
    missing = client.patch(BASE + '/admin/categories/' + str(uuid4()), headers=headers, json={'active': False})
    error(missing, 404, 'NOT_FOUND')
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM audit_logs')) == 4


def test_report_creation_review_and_statistics(client, auth_runtime):
    admin, headers = login(client)
    b, c = create_refs(client, headers)
    key = item(auth_runtime, admin, b, c)
    path = BASE + f'/found-items/{key}/reports'
    with TestClient(client.app, base_url='https://testserver') as member:
        error(member.post(path, json={'reasonCode': 'SPAM', 'details': '신고'}), 401, 'AUTH_REQUIRED')
        _, member_headers = login(member, 'student-01')
        response = member.post(path, headers=member_headers, json={'reasonCode': 'SPAM', 'details': '신고'})
        assert response.status_code == 201, response.text
        report_id = response.json()['reportId']
        error(member.post(path, headers=member_headers, json={'reasonCode': 'OTHER', 'details': '중복'}),
              409, 'OPEN_REPORT_EXISTS')
        review = BASE + f'/admin/post-reports/{report_id}/review'
        result = client.post(review, headers=headers, json={'decision': 'HIDE'})
        assert result.status_code == 200, result.text
        assert result.json()['status'] == 'REVIEWED'
        assert result.json()['reviewedAt'].endswith('+09:00')
        error(client.post(review, headers=headers, json={'decision': 'DISMISS'}), 409, 'REPORT_ALREADY_REVIEWED')
        error(member.post(path, headers=member_headers, json={'reasonCode': 'SPAM', 'details': '숨김'}),
              404, 'NOT_FOUND')
    assert client.get(BASE + f'/admin/post-reports/{report_id}').json()['reportId'] == report_id
    assert client.get(BASE + f'/admin/post-reports?itemId={key}&status=REVIEWED').json()['totalElements'] == 1
    item(auth_runtime, admin, b, c, status='COLLECTED', closed=auth_runtime.clock(), purge=auth_runtime.clock()+timedelta(days=365))
    item(auth_runtime, admin, b, c, status='EXPIRED', closed=auth_runtime.clock(), purge=auth_runtime.clock()+timedelta(days=365))
    item(auth_runtime, admin, b, c, deleted=auth_runtime.clock(), purge=auth_runtime.clock()+timedelta(days=365))
    stats = client.get(BASE + '/admin/statistics').json()
    assert (stats['postedCount'], stats['collectedCount'], stats['expiredCount']) == (1, 1, 1)
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(text('SELECT hidden FROM found_items WHERE id=:id'), dict(id=key)) is True
        assert db.scalar(text("SELECT count(*) FROM audit_logs WHERE action IN ('POST_HIDDEN','POST_REPORT_REVIEWED')")) == 2


def test_dispute_review_restriction_and_release_after_purge(client, auth_runtime):
    admin, headers = login(client)
    with TestClient(client.app, base_url='https://testserver') as member:
        collector, _ = login(member, 'student-01')
    b, c = create_refs(client, headers)
    key = item(auth_runtime, admin, b, c)
    collection, report = dispute(auth_runtime, admin, collector, key)
    review = BASE + f'/admin/disputes/{report}/review'
    restriction = BASE + f'/admin/users/{collector}/collection-restriction'
    error(client.put(restriction, headers=headers, json={'restricted': True}), 400, 'VALIDATION_ERROR')
    error(client.put(restriction, headers=headers, json={'restricted': True, 'disputeId': report}), 409, 'DISPUTE_NOT_UPHELD')
    error(client.post(review, headers=headers, json={'decision': 'DISMISSED', 'blockCollector': True}), 400, 'INVALID_DECISION')
    assert client.get(BASE + '/admin/disputes').json()['totalElements'] == 1
    response = client.post(review, headers=headers, json={'decision': 'UPHELD', 'blockCollector': True})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'RESOLVED'
    error(client.post(review, headers=headers, json={'decision': 'UPHELD', 'blockCollector': True}), 409, 'DISPUTE_ALREADY_RESOLVED')
    assert client.get(BASE + '/admin/disputes').json()['totalElements'] == 0
    assert client.get(BASE + f'/admin/disputes/{report}').json()['collectorId'] == collector
    error(client.put(BASE + f'/admin/users/{admin}/collection-restriction', headers=headers,
        json={'restricted': True, 'disputeId': report}), 409, 'COLLECTOR_MISMATCH')
    repeat = client.put(restriction, headers=headers, json={'restricted': True, 'disputeId': report})
    assert repeat.status_code == 200, repeat.text
    with auth_runtime.sync_engine.begin() as db:
        assert db.scalar(text('SELECT undone_at FROM collections WHERE id=:id'), dict(id=collection)) is None
        db.execute(text('DELETE FROM collections WHERE id=:id'), dict(id=collection))
        row = db.execute(text('SELECT restricted, source_dispute_id FROM collection_restrictions WHERE user_id=:id'), dict(id=collector)).one()
        assert row == (True, None)
    released = client.put(restriction, headers=headers, json={'restricted': False})
    assert released.status_code == 200, released.text
    assert released.json()['disputeId'] is None
    assert released.json()['restricted'] is False
    logs = client.get(BASE + f'/admin/audit-logs?targetId={collector}').json()['items']
    assert len(logs) == 2
    assert any(log['metadata'] == {'restricted': False} for log in logs)
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM audit_logs WHERE purge_after != occurred_at + interval '1 year'")) == 0


def test_audit_filters_and_failure_rolls_back_change(client, auth_runtime, monkeypatch):
    _, headers = login(client)
    b, _ = create_refs(client, headers)
    error(client.get(BASE + '/admin/audit-logs?from=2026-11-04T00:00:00%2B09:00&to=2026-11-03T00:00:00%2B09:00'),
          400, 'INVALID_TIME_RANGE')
    error(client.get(BASE + '/admin/audit-logs?from=2026-11-03T00:00:00'), 400, 'VALIDATION_ERROR')
    logs = client.get(BASE + f'/admin/audit-logs?targetId={b}&action=REFERENCE_CREATED').json()
    assert logs['totalElements'] == 1
    assert logs['items'][0]['metadata'] == {}
    assert logs['items'][0]['occurredAt'].endswith('+09:00')
    def fail(db, actor, action, kind, target, now, **metadata):
        # Failure occurs at flush/commit, after the resource was modified.
        db.add(AuditLog(actor_id=actor.id, actor_type='ADMIN', action='BAD', target_type=kind,
            target_id=target, event_metadata={}, occurred_at=now, purge_after=now+timedelta(days=365)))
    monkeypatch.setattr(admin_service, 'append_audit', fail)
    error(client.patch(BASE + f'/admin/buildings/{b}', headers=headers, json={'active': False}),
          500, 'INTERNAL_SERVER_ERROR')
    assert client.get(BASE + '/admin/buildings').json()['items'][0]['active'] is True


def test_expired_session_is_removed(client, auth_runtime):
    login(client)
    auth_runtime.clock.advance(minutes=30)
    error(client.get(BASE + '/admin/users'), 401, 'SESSION_EXPIRED')
    assert not client.cookies.get('KAIFIND_SESSION')
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM sessions')) == 0


def test_concurrent_self_demotions_preserve_last_admin(client, auth_runtime):
    first, headers1 = login(client)
    with TestClient(client.app, base_url='https://testserver') as other:
        second, headers2 = login(other, 'faculty-01')
        assert client.patch(BASE + f'/admin/users/{second}/role', headers=headers1, json={'role': 'ADMIN'}).status_code == 200
        def demote(args):
            browser, key, headers = args
            return browser.patch(BASE + f'/admin/users/{key}/role', headers=headers, json={'role': 'MEMBER'})
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(demote, [(client, first, headers1), (other, second, headers2)]))
        assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM users WHERE role='ADMIN'")) == 1


def test_concurrent_report_review_has_one_winner(client, auth_runtime):
    admin, headers1 = login(client)
    b, c = create_refs(client, headers1)
    key = item(auth_runtime, admin, b, c)
    response = client.post(BASE + f'/found-items/{key}/reports', headers=headers1,
        json={'reasonCode': 'OTHER', 'details': '검토 요청'})
    path = BASE + '/admin/post-reports/' + response.json()['reportId'] + '/review'
    with TestClient(client.app, base_url='https://testserver') as other:
        _, headers2 = login(other)
        def review(args):
            browser, headers = args
            return browser.post(path, headers=headers, json={'decision': 'HIDE'})
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(review, [(client, headers1), (other, headers2)]))
        assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]


def test_release_without_existing_restriction_and_same_state_is_idempotent(client, auth_runtime):
    admin, headers = login(client)
    path = BASE + f'/admin/users/{admin}/collection-restriction'
    first = client.put(path, headers=headers, json={'restricted': False})
    assert first.status_code == 200, first.text
    assert first.json()['disputeId'] is None
    second = client.put(path, headers=headers, json={'restricted': False})
    assert second.json() == first.json()
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM audit_logs WHERE action='COLLECTION_RESTRICTION_CHANGED'")) == 1


def test_concurrent_dispute_review_and_reference_create(client, auth_runtime):
    admin, headers1 = login(client)
    with TestClient(client.app, base_url='https://testserver') as other:
        collector, _ = login(other, 'student-01')
        _, headers2 = login(other)
        b, c = create_refs(client, headers1)
        key = item(auth_runtime, admin, b, c)
        _, report = dispute(auth_runtime, admin, collector, key)
        def review(args):
            browser, headers = args
            return browser.post(BASE + f'/admin/disputes/{report}/review', headers=headers,
                json={'decision': 'UPHELD', 'blockCollector': True})
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(review, [(client, headers1), (other, headers2)]))
        assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
        def create(args):
            browser, headers = args
            return browser.post(BASE + '/admin/categories', headers=headers,
                json={'nameKo': '휴대전화', 'nameEn': 'Phone', 'sensitive': True})
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(create, [(client, headers1), (other, headers2)]))
        assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]
        assert next(r for r in results if r.status_code == 409).json()['code'] == 'CATEGORY_NAME_EXISTS'
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM audit_logs WHERE action='DISPUTE_REVIEWED'")) == 1
        assert db.scalar(text("SELECT count(*) FROM audit_logs WHERE action='COLLECTION_RESTRICTION_CHANGED'")) == 1


def test_category_rename_conflict_immutability_and_existing_reference(client, auth_runtime):
    admin, headers = login(client)
    b, c = create_refs(client, headers)
    key = item(auth_runtime, admin, b, c)
    created = client.post(BASE + '/admin/categories', headers=headers,
        json={'nameKo': '전화기', 'nameEn': 'Phone', 'sensitive': True}).json()['categoryId']
    error(client.patch(BASE + f'/admin/categories/{created}', headers=headers,
        json={'nameEn': 'WALLET'}), 409, 'CATEGORY_NAME_EXISTS')
    error(client.patch(BASE + f'/admin/categories/{c}', headers=headers,
        json={'sensitive': False}), 400, 'VALIDATION_ERROR')
    assert client.patch(BASE + f'/admin/categories/{c}', headers=headers, json={'active': False}).status_code == 200
    with auth_runtime.sync_engine.connect() as db:
        row = db.execute(text('SELECT category_id, found_building_id FROM found_items WHERE id=:id'), dict(id=key)).one()
        assert tuple(map(str, row)) == (c, b)
