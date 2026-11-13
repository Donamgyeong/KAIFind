"""ITEM-03 with actual PostgreSQL, photo upload, and MinIO attachment storage."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from main import app as full_app
from service.photos import PhotoRuntime, PhotoSettings
from service.text_analysis_profiles import initialize_policy
from test_analysis_worker import PROFILE, analysis_env, worker
from test_matching_service import drain
from test_photo_contract import storage, login, upload, error


BASE = '/api/v1/found-items'


@pytest.fixture
def context(analysis_env, auth_runtime, storage):
    env = analysis_env
    with env.sync.begin() as db:
        db.execute(text('DELETE FROM found_items'))
        db.execute(text('DELETE FROM lost_reports'))

    async def prepare():
        async with env.factory() as db, db.begin():
            await initialize_policy(db, PROFILE, now=env.clock())
    asyncio.run(prepare())
    app = FastAPI()
    app.state.auth_runtime = auth_runtime
    app.state.photo_runtime = PhotoRuntime(PhotoSettings(public_base_url='https://testserver'), lambda: storage)
    app.router.routes.extend(full_app.routes)
    with TestClient(app, base_url='https://testserver') as client:
        user_id, headers = login(client)
        response = upload(client, headers)
        assert response.status_code == 201, response.text
        body = {
            'categoryId': str(env.ids['category']), 'title': ' Wallet ', 'description': ' black wallet ',
            'foundBuildingId': str(env.ids['building']), 'foundLocationDescription': ' Lobby ',
            'foundAt': env.clock().isoformat(),
            'photos': [{'photoId': response.json()['photoId'], 'altText': ' wallet photo '}],
            'dropOff': {'mode': 'KEPT_BY_FINDER'},
        }
        yield client, env, body, headers, storage


def create(context):
    client, env, body, headers, storage = context
    response = client.post(BASE, json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response


def test_registration_response_and_atomic_records(context):
    client, env, body, headers, storage = context
    response = create(context)
    result = response.json()
    assert response.headers['location'] == BASE + '/' + result['itemId']
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['content-language'] == 'ko'
    assert result['title'] == 'Wallet' and result['description'] == 'black wallet'
    assert result['analysisStatus'] == 'PENDING' and result['status'] == 'POSTED'
    assert result['closedAt'] is None and not result['hidden']
    assert result['createdAt'].endswith('+09:00')
    assert 'dropOff' not in result and 'email' not in result['finder']
    assert set(result['photos'][0]) == {'photoId', 'altText', 'accessRequiresLogin'}
    with env.sync.connect() as db:
        params = {'id': result['itemId']}
        assert db.execute(text('SELECT count(*) FROM drop_off_versions WHERE item_id=:id'), params).scalar_one() == 1
        assert db.execute(text('SELECT count(*) FROM found_item_text_features WHERE item_id=:id'), params).scalar_one() == 1
        assert db.execute(text('SELECT count(*) FROM keyword_registration_events WHERE item_id=:id'), params).scalar_one() == 1
        assert db.execute(text('SELECT count(*) FROM match_evaluation_jobs WHERE item_id=:id'), params).scalar_one() == 1
        assert db.execute(text('SELECT unattached_expires_at FROM photos WHERE id=:id'),
                          {'id': body['photos'][0]['photoId']}).scalar_one() is None
    error(client.post(BASE, json=body, headers=headers), 409, 'PHOTO_ALREADY_ATTACHED')
    # Other item APIs retain their existing implementation status.
    assert client.get(response.headers['location']).status_code == 501


def test_drop_off_and_sensitive_photo_protection(context):
    client, env, body, headers, storage = context
    with env.sync.begin() as db:
        sensitive_id = uuid4()
        db.execute(text("INSERT INTO categories (id,name_ko,name_en,sensitive) VALUES (:id,'민감','Sensitive',true)"),
                   {'id': sensitive_id})
        body['categoryId'] = str(sensitive_id)
    photo = upload(client, headers, purpose='DROP_OFF').json()['photoId']
    body['dropOff'] = {
        'mode': 'DROP_OFF', 'buildingId': body['foundBuildingId'],
        'spotDescription': 'PRIVATE STORAGE', 'photo': {'photoId': photo, 'altText': 'storage'},
    }
    response = create(context)
    assert 'PRIVATE STORAGE' not in response.text
    assert response.json()['sensitive'] and response.json()['photos'][0]['accessRequiresLogin']
    assert len(response.json()['photos']) == 1
    with env.sync.connect() as db:
        assert db.execute(text('SELECT count(*) FROM photo_attachments WHERE sensitive_latched')).scalar_one() == 2
        assert db.execute(text('SELECT sensitive_latched FROM drop_off_versions')).scalar_one()


@pytest.mark.parametrize('patch', [
    {'title': ' '}, {'description': None}, {'foundAt': '2099-01-01T00:00:00+09:00'},
    {'photos': []}, {'foundAt': 1}, {'foundAt': '2026-11-01T00:00:00'},
    {'dropOff': {'mode': 'KEPT_BY_FINDER', 'photo': None}}, {'status': 'POSTED'},
    {'dropOff': {'mode': 'DROP_OFF'}},
])
def test_invalid_registration(context, patch):
    client, env, body, headers, storage = context
    error(client.post(BASE, json={**body, **patch}, headers=headers), 400, 'VALIDATION_ERROR')
    with env.sync.connect() as db:
        assert db.execute(text('SELECT count(*) FROM found_items')).scalar_one() == 0


@pytest.mark.parametrize('case', ['inactive', 'missing', 'purpose', 'expired', 'foreign'])
def test_reference_and_photo_errors_roll_back(context, case):
    client, env, body, headers, storage = context
    expected = (400, 'INVALID_REFERENCE')
    with env.sync.begin() as db:
        if case == 'inactive':
            db.execute(text('UPDATE buildings SET active=false WHERE id=:id'), {'id': body['foundBuildingId']})
        elif case == 'missing':
            body['categoryId'] = str(uuid4())
        elif case == 'purpose':
            db.execute(text("UPDATE photos SET purpose='DROP_OFF' WHERE id=:id"), {'id': body['photos'][0]['photoId']})
        elif case == 'expired':
            db.execute(text('UPDATE photos SET unattached_expires_at=:now WHERE id=:id'),
                       {'now': env.clock(), 'id': body['photos'][0]['photoId']})
    if case == 'foreign':
        _, headers = login(client, 'faculty-01')
        expected = (403, 'PHOTO_FORBIDDEN')
    error(client.post(BASE, json=body, headers=headers), *expected)
    with env.sync.connect() as db:
        for table in ('found_items', 'drop_off_versions', 'photo_attachments', 'found_item_text_features', 'keyword_registration_events'):
            assert db.execute(text(f'SELECT count(*) FROM {table}')).scalar_one() == 0


@pytest.mark.parametrize('target', ['analysis', 'audit', 'photo'])
def test_downstream_failure_rolls_back_everything(context, monkeypatch, target):
    client, env, body, headers, storage = context

    async def fail_async(*args, **kwargs):
        raise RuntimeError('simulated failure')

    def fail_sync(*args, **kwargs):
        raise RuntimeError('simulated failure')

    name = {'analysis': 'request_found_item_analysis', 'audit': 'append_audit', 'photo': 'attach_photo'}[target]
    monkeypatch.setattr('service.found_items.' + name, fail_sync if target == 'audit' else fail_async)
    error(client.post(BASE, json=body, headers=headers), 500, 'INTERNAL_SERVER_ERROR')
    with env.sync.connect() as db:
        for table in ('found_items', 'drop_off_versions', 'photo_attachments', 'found_item_text_features', 'keyword_registration_events'):
            assert db.execute(text(f'SELECT count(*) FROM {table}')).scalar_one() == 0
        assert db.execute(text('SELECT unattached_expires_at FROM photos WHERE id=:id'),
                          {'id': body['photos'][0]['photoId']}).scalar_one() is not None


def test_concurrent_photo_reuse(context):
    client, env, body, headers, storage = context
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: client.post(BASE, json=body, headers=headers), range(2)))
    assert sorted(result.status_code for result in results) == [201, 409]


def test_authentication_and_openapi(context):
    client, env, body, headers, storage = context
    error(client.post(BASE, json=body), 403, 'CSRF_INVALID')
    error(client.post(BASE, json=body, headers={**headers, 'Origin': 'https://evil.example'}), 403, 'ORIGIN_NOT_ALLOWED')
    error(client.post(BASE, content='{}', headers={**headers, 'Content-Type': 'text/plain'}), 415, 'UNSUPPORTED_MEDIA_TYPE')
    schema = client.get('/openapi.json').json()
    assert '501' not in schema['paths'][BASE]['post']['responses']
    assert schema['paths'][BASE]['post']['responses']['201']
    client.cookies.clear()
    error(client.post(BASE, json=body), 401, 'AUTH_REQUIRED')


@pytest.mark.parametrize('item_first', [False, True])
@pytest.mark.parametrize('real', [False, pytest.param(True, marks=pytest.mark.skipif(
    os.getenv('RUN_REAL_TEXT_ANALYSIS_TESTS') != 'true', reason='Real model opt-in',
))])
def test_both_http_registration_matching(context, item_first, real):
    client, env, body, headers, storage = context

    async def process():
        runtime = None
        try:
            if real:
                from library.translation_runtime import TranslationRuntime, TranslationSettings
                runtime = TranslationRuntime(TranslationSettings.from_environment())
                await runtime.start()
                env.runtime = runtime
                async with env.factory() as db, db.begin():
                    await db.execute(text('DELETE FROM matching_runtime'))
                    await initialize_policy(db, runtime.profile, now=env.clock())
            body['description'] = '검은 지갑입니다.'
            # Different buildings force actual keyword matching rather than building fallback.
            other = uuid4()
            with env.sync.begin() as db:
                db.execute(text("INSERT INTO buildings (id,code,name_ko,name_en) VALUES (:id,:code,'다른 건물','Other')"),
                           {'id': other, 'code': other.hex})
            if item_first:
                item = create(context).json()
            _, report_headers = login(client, 'faculty-01')
            report_response = client.post('/api/v1/lost-reports', headers=report_headers, json={
                'categoryId': body['categoryId'], 'description': '검은 지갑입니다.',
                'possibleBuildingIds': [str(other)], 'lostDateFrom': '2026-11-01',
                'lostDateTo': '2026-11-01', 'privateIdentifyingDetails': 'PRIVATE SECRET',
            })
            assert report_response.status_code == 201, report_response.text
            report_id = report_response.json()['reportId']
            if not item_first:
                _, item_headers = login(client, 'student-01')
                headers.update(item_headers)
                item = create(context).json()
            while await worker(env).run_once():
                pass
            await drain(env)
            login(client, 'faculty-01')
            path = f'/api/v1/lost-reports/{report_id}/matches'
            result = client.get(path)
            assert result.status_code == 200, result.text
            data = result.json()
            assert data['isComplete'] and data['matchingStatus'] == 'READY'
            assert data['totalElements'] == 1
            assert data['items'][0]['itemId'] == item['itemId']
            assert data['items'][0]['matchedBy'] == ['KEYWORD']
            assert 'PRIVATE SECRET' not in result.text
            await drain(env)
            assert client.get(path).json() == data
            with env.sync.connect() as db:
                assert db.execute(text("SELECT count(*) FROM notifications WHERE type='MATCH_CANDIDATE' AND report_id=:id"),
                                  {'id': report_id}).scalar_one() == 1
        finally:
            if runtime:
                await runtime.close()
    asyncio.run(process())
