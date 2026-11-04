"""Photo acceptance tests against migrated PostgreSQL and a private MinIO bucket."""
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from io import BytesIO
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from minio import Minio
from minio.error import S3Error
from PIL import Image
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session as SyncSession

from library.photo_storage import PhotoStorage, StorageSettings
from main import app as full_app
from model import AuditLog, Category, FoundItem, Photo, PhotoAttachment, PhotoUploadIntent, User
from service.auth import AuthError
from service.photo_attachments import attach_photo
from service.photo_cleanup import cleanup
from service.photos import PhotoRuntime, PhotoSettings
from test_photo_images import image_bytes

BASE = '/api/v1'


@pytest.fixture
def storage():
    endpoint = os.getenv('TEST_MINIO_ENDPOINT')
    if not endpoint:
        pytest.skip('TEST_MINIO_ENDPOINT is required for real MinIO photo tests')
    bucket = 'kaifind-test-' + uuid4().hex
    settings = StorageSettings(endpoint, os.environ['TEST_MINIO_ACCESS_KEY'],
        os.environ['TEST_MINIO_SECRET_KEY'], bucket=bucket,
        secure=os.getenv('TEST_MINIO_SECURE', 'false') == 'true')
    adapter = PhotoStorage(settings)
    adapter.client.make_bucket(bucket)
    yield adapter
    for obj in adapter.client.list_objects(bucket, recursive=True):
        adapter.client.remove_object(bucket, obj.object_name)
    adapter.client.remove_bucket(bucket)


@pytest.fixture
def client(auth_runtime, storage):
    app = FastAPI()
    app.state.auth_runtime = auth_runtime
    app.state.photo_runtime = PhotoRuntime(PhotoSettings(public_base_url='https://testserver'), lambda: storage)
    for route in full_app.routes:
        app.router.routes.append(route)
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('TRUNCATE buildings, categories, audit_logs, photo_upload_intents CASCADE'))
    with TestClient(app, base_url='https://testserver') as client:
        yield client


def login(client, key='student-01'):
    csrf = client.get(BASE + '/auth/csrf').json()['csrfToken']
    response = client.post(BASE + '/auth/mock/login', json={'mockAccountId': key},
        headers={'X-CSRF-Token': csrf})
    assert response.status_code == 200, response.text
    return response.json()['user']['userId'], {'X-CSRF-Token': response.json()['csrfToken']}


def upload(client, headers, purpose='ITEM', raw=None, **kwargs):
    return client.post(BASE + '/photos', headers=headers,
        files={'file': ('untrusted.exe', raw if raw is not None else image_bytes(), 'text/plain')},
        data={'purpose': purpose}, **kwargs)


def error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()['code'] == code, response.text
    assert set(response.json()) == {'code', 'message', 'fieldErrors'}
    assert response.headers['cache-control'] == 'private, no-store'


def issue(client, headers, photo_id):
    response = client.post(f'{BASE}/photos/{photo_id}/access-url', headers=headers)
    assert response.status_code == 200, response.text
    return urlsplit(response.json()['url']).path


def attach(rt, photo_id, *, sensitive=False, purpose='ITEM'):
    ids = dict(item=uuid4(), building=uuid4(), category=uuid4(), version=uuid4())
    with rt.sync_engine.begin() as db:
        uploader = db.scalar(text('SELECT uploader_id FROM photos WHERE id=:id'), {'id': photo_id})
        db.execute(text("INSERT INTO buildings (id,code,name_ko,name_en) VALUES (:id,:code,'건물','Building')"),
                   dict(id=ids['building'], code=uuid4().hex))
        db.execute(text("INSERT INTO categories (id,name_ko,name_en,sensitive) VALUES (:id,:name,:name,:sensitive)"),
                   dict(id=ids['category'], name=uuid4().hex, sensitive=sensitive))
        db.execute(text('''INSERT INTO found_items (id,finder_id,category_id,found_building_id,title,
            description,found_location_description,found_at,expires_at)
            VALUES (:id,:finder,:category,:building,'물품','설명','장소',:now,:expires)'''),
            dict(id=ids['item'], finder=uploader, category=ids['category'], building=ids['building'],
                 now=rt.clock(), expires=rt.clock()+timedelta(days=30)))
        if purpose == 'DROP_OFF':
            db.execute(text('''INSERT INTO drop_off_versions (id,item_id,revision_no,mode,building_id,
                spot_description,changed_by_user_id) VALUES (:id,:item,1,'DROP_OFF',:building,'위치',:user)'''),
                dict(id=ids['version'], item=ids['item'], building=ids['building'], user=uploader))
        db.execute(text('''INSERT INTO photo_attachments (photo_id,item_id,drop_off_version_id,
            alt_text,display_order,sensitive_latched) VALUES (:photo,:item,:version,'사진',:display,:sensitive)'''),
            dict(photo=photo_id, item=ids['item'], version=ids['version'] if purpose == 'DROP_OFF' else None,
                 display=None if purpose == 'DROP_OFF' else 0, sensitive=sensitive))
        db.execute(text('UPDATE photos SET unattached_expires_at=NULL WHERE id=:id'), {'id': photo_id})
    return ids


def change_category(rt, item_id, sensitive):
    category = uuid4()
    with rt.sync_engine.begin() as db:
        db.execute(text('INSERT INTO categories (id,name_ko,name_en,sensitive) VALUES (:id,:name,:name,:sensitive)'),
                   dict(id=category, name=uuid4().hex, sensitive=sensitive))
        db.execute(text('UPDATE found_items SET category_id=:category WHERE id=:item'),
                   dict(category=category, item=item_id))


def test_upload_auth_csrf_origin_and_multipart_guards(client, auth_runtime, storage):
    error(upload(client, {}), 401, 'AUTH_REQUIRED')
    _, headers = login(client)
    error(upload(client, {}), 403, 'CSRF_INVALID')
    error(upload(client, dict(headers, Origin='https://evil.test')), 403, 'ORIGIN_NOT_ALLOWED')
    error(client.post(BASE+'/photos', headers=headers, json={}), 415, 'PHOTO_MULTIPART_REQUIRED')
    error(upload(client, headers, purpose='OTHER'), 400, 'VALIDATION_ERROR')
    error(client.post(BASE+'/photos', headers=headers,
        files={'file': ('a.png', image_bytes())}, data={'purpose': 'ITEM', 'extra': 'value'}), 400, 'VALIDATION_ERROR')
    error(client.post(BASE+'/photos', headers=headers, content=b'broken',
        **{}), 415, 'PHOTO_MULTIPART_REQUIRED')
    assert list(storage.client.list_objects(storage.bucket)) == []
    auth_runtime.clock.advance(minutes=31)
    error(upload(client, headers), 401, 'SESSION_EXPIRED')


@pytest.mark.parametrize('fmt', ['JPEG', 'PNG', 'WEBP'])
def test_upload_stores_only_sanitized_bytes_and_owner_can_preview(client, auth_runtime, storage, fmt):
    user, headers = login(client)
    response = upload(client, headers, raw=image_bytes(fmt, metadata=True))
    assert response.status_code == 201, response.text
    data = response.json()
    assert set(data) == {'photoId','purpose','contentType','sizeBytes','width','height','unattachedExpiresAt'}
    assert (data['width'], data['height']) == (12, 16)
    with auth_runtime.sync_engine.connect() as db:
        row = db.execute(text('SELECT * FROM photos WHERE id=:id'), {'id': data['photoId']}).mappings().one()
        assert str(row['uploader_id']) == user
        assert db.scalar(text('SELECT count(*) FROM photo_upload_intents')) == 0
        key = row['object_key']
    content = storage.read(key)
    assert len(content) == data['sizeBytes']
    with Image.open(BytesIO(content)) as decoded:
        decoded.load()
        assert not decoded.getexif()
        assert 'location' not in decoded.info
    path = issue(client, headers, data['photoId'])
    image = client.get(path)
    assert image.status_code == 200
    assert image.content == content
    assert image.headers['content-type'] == data['contentType']
    assert int(image.headers['content-length']) == len(content)
    assert image.headers['cache-control'] == 'private, no-store'
    assert image.headers['x-content-type-options'] == 'nosniff'
    error(client.get(path, headers={'Range': 'bytes=0-1'}), 405, 'PHOTO_METHOD_NOT_ALLOWED')
    assert client.head(path).status_code == 405
    # No anonymous object policy: an unsigned MinIO GET cannot read the object.
    anonymous = Minio(storage.client._base_url.host, secure=storage.client._base_url.is_https)
    with pytest.raises(S3Error) as denied:
        anonymous.get_object(storage.bucket, key)
    assert denied.value.code in {'AccessDenied', 'AllAccessDisabled'}


def test_invalid_files_and_bounded_chunked_upload(client):
    _, headers = login(client)
    for raw in (b'', b'<script>bad</script>', b'\xff\xd8\xffbroken'):
        error(upload(client, headers, raw=raw), 422, 'INVALID_IMAGE')
    runtime = client.app.state.photo_runtime
    runtime.settings = replace(runtime.settings, max_bytes=100)
    error(upload(client, headers, raw=b'x'*101), 413, 'PHOTO_TOO_LARGE')
    boundary = 'testboundary'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\nITEM\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="x.png"\r\n'
            'Content-Type: image/png\r\n\r\n').encode() + b'x'*70000
    response = client.post(BASE+'/photos', headers=dict(headers,
        **{'Content-Type': f'multipart/form-data; boundary={boundary}'}),
        content=(body[i:i+1024] for i in range(0, len(body), 1024)))
    error(response, 413, 'PHOTO_TOO_LARGE')


def test_unattached_permissions_session_binding_and_expiry(client, auth_runtime):
    _, headers = login(client)
    photo = upload(client, headers).json()['photoId']
    path = issue(client, headers, photo)
    with TestClient(client.app, base_url='https://testserver') as other:
        error(other.get(path), 401, 'AUTH_REQUIRED')
        _, other_headers = login(other, 'faculty-01')
        error(other.post(f'{BASE}/photos/{photo}/access-url', headers=other_headers), 403, 'PHOTO_FORBIDDEN')
        error(other.get(path), 403, 'PHOTO_FORBIDDEN')
        # Even another login session of the same uploader cannot use the link.
        login(other)
        error(other.get(path), 403, 'PHOTO_FORBIDDEN')
    auth_runtime.clock.advance(seconds=59)
    assert client.get(path).status_code == 200
    auth_runtime.clock.advance(seconds=1)
    error(client.get(path), 410, 'PHOTO_LINK_EXPIRED')
    error(client.get(BASE+'/photo-access/'+'x'*43), 404, 'NOT_FOUND')
    error(client.get(BASE+'/photo-access/bad'), 404, 'NOT_FOUND')


def test_public_photo_anonymous_csrf_and_current_visibility(client, auth_runtime):
    owner, headers = login(client)
    photo = upload(client, headers).json()['photoId']
    ids = attach(auth_runtime, photo)
    with TestClient(client.app, base_url='https://testserver') as anon:
        error(anon.post(f'{BASE}/photos/{photo}/access-url'), 403, 'CSRF_INVALID')
        csrf = anon.get(BASE+'/auth/csrf').json()['csrfToken']
        path = issue(anon, {'X-CSRF-Token': csrf}, photo)
        anon.cookies.clear()
        assert anon.get(path).status_code == 200
        with auth_runtime.sync_engine.begin() as db:
            db.execute(text('UPDATE found_items SET hidden=true WHERE id=:id'), {'id': ids['item']})
        error(anon.get(path), 404, 'NOT_FOUND')
        # Owner may still access hidden items.
        assert client.get(path).status_code == 200
        with auth_runtime.sync_engine.begin() as db:
            db.execute(text('UPDATE found_items SET deleted_at=:now WHERE id=:id'),
                       dict(now=auth_runtime.clock(), id=ids['item']))
        error(client.get(path), 404, 'NOT_FOUND')


def test_sensitive_audit_session_binding_and_latched_protection(client, auth_runtime):
    _, headers = login(client)
    photo = upload(client, headers).json()['photoId']
    ids = attach(auth_runtime, photo, sensitive=True)
    path = issue(client, headers, photo)
    for _ in range(2):
        assert client.get(path).status_code == 200
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM audit_logs WHERE action='PHOTO_ACCESS_URL_ISSUED'")) == 1
        assert db.scalar(text("SELECT count(*) FROM audit_logs WHERE action='SENSITIVE_PHOTO_VIEWED'")) == 2
    with TestClient(client.app, base_url='https://testserver') as other:
        login(other, 'faculty-01')
        error(other.get(path), 403, 'PHOTO_FORBIDDEN')
    change_category(auth_runtime, ids['item'], False)
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('UPDATE photo_attachments SET detached_at=:now WHERE photo_id=:id'),
                   dict(now=auth_runtime.clock(), id=photo))
    with TestClient(client.app, base_url='https://testserver') as anon:
        csrf = anon.get(BASE+'/auth/csrf').json()['csrfToken']
        error(anon.post(f'{BASE}/photos/{photo}/access-url', headers={'X-CSRF-Token':csrf}), 401, 'AUTH_REQUIRED')
    assert client.get(path).status_code == 200


def test_public_grant_becomes_protected_after_category_change(client, auth_runtime):
    _, headers = login(client)
    photo = upload(client, headers).json()['photoId']
    ids = attach(auth_runtime, photo)
    with TestClient(client.app, base_url='https://testserver') as anon:
        csrf = anon.get(BASE+'/auth/csrf').json()['csrfToken']
        path = issue(anon, {'X-CSRF-Token':csrf}, photo)
        assert anon.get(path).status_code == 200
        change_category(auth_runtime, ids['item'], True)
        error(anon.get(path), 401, 'AUTH_REQUIRED')
        error(client.get(path), 403, 'PHOTO_FORBIDDEN')


def test_historical_dropoff_photo_requires_member(client, auth_runtime):
    _, headers = login(client)
    photo = upload(client, headers, purpose='DROP_OFF').json()['photoId']
    attach(auth_runtime, photo, purpose='DROP_OFF')
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('UPDATE photo_attachments SET detached_at=:now WHERE photo_id=:id'),
                   dict(now=auth_runtime.clock(), id=photo))
    with TestClient(client.app, base_url='https://testserver') as other:
        csrf = other.get(BASE+'/auth/csrf').json()['csrfToken']
        error(other.post(f'{BASE}/photos/{photo}/access-url', headers={'X-CSRF-Token':csrf}), 401, 'AUTH_REQUIRED')
        _, headers2 = login(other, 'faculty-01')
        path = issue(other, headers2, photo)
        assert other.get(path).status_code == 200


def test_audit_commit_failure_returns_no_image_bytes(client, auth_runtime):
    _, headers = login(client)
    photo = upload(client, headers).json()['photoId']
    attach(auth_runtime, photo, sensitive=True)
    path = issue(client, headers, photo)
    def fail_commit(session):
        if any(isinstance(row, AuditLog) and row.action == 'SENSITIVE_PHOTO_VIEWED' for row in session.new):
            raise RuntimeError('synthetic audit commit failure')
    event.listen(SyncSession, 'before_commit', fail_commit)
    try:
        response = client.get(path)
    finally:
        event.remove(SyncSession, 'before_commit', fail_commit)
    error(response, 500, 'INTERNAL_SERVER_ERROR')
    assert response.headers['content-type'].startswith('application/json')
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM audit_logs WHERE action='SENSITIVE_PHOTO_VIEWED'")) == 0
    assert client.get(path).status_code == 200


def test_upload_database_failure_compensates_object(client, auth_runtime, storage):
    _, headers = login(client)
    def fail_commit(session):
        # flush in upload means the new Photo is in the identity map at COMMIT.
        if any(isinstance(row, Photo) for row in session.identity_map.values()):
            raise RuntimeError('synthetic photo commit failure')
    event.listen(SyncSession, 'before_commit', fail_commit)
    try:
        response = upload(client, headers)
    finally:
        event.remove(SyncSession, 'before_commit', fail_commit)
    error(response, 500, 'INTERNAL_SERVER_ERROR')
    assert list(storage.client.list_objects(storage.bucket)) == []
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM photos')) == 0
        assert db.scalar(text('SELECT count(*) FROM photo_upload_intents')) == 0


def test_failed_compensation_is_recovered_by_scheduled_cleanup(client, auth_runtime, storage, monkeypatch):
    _, headers = login(client)
    original_delete = storage.delete
    def fail_delete(key):
        raise ConnectionError('synthetic storage failure')
    monkeypatch.setattr(storage, 'delete', fail_delete)
    def fail_commit(session):
        if any(isinstance(row, Photo) for row in session.identity_map.values()):
            raise RuntimeError('synthetic commit failure')
    event.listen(SyncSession, 'before_commit', fail_commit)
    try:
        error(upload(client, headers), 500, 'INTERNAL_SERVER_ERROR')
    finally:
        event.remove(SyncSession, 'before_commit', fail_commit)
    assert len(list(storage.client.list_objects(storage.bucket))) == 1
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM photo_upload_intents')) == 1
    monkeypatch.setattr(storage, 'delete', original_delete)
    auth_runtime.clock.advance(hours=2)
    result = asyncio.run(cleanup(auth_runtime.factory, storage, auth_runtime.clock()))
    assert result['intents'] == 1
    assert list(storage.client.list_objects(storage.bucket)) == []
    assert asyncio.run(cleanup(auth_runtime.factory, storage, auth_runtime.clock()))['intents'] == 0


def test_storage_failure_never_creates_photo_and_missing_object_is_json(client, auth_runtime, storage, monkeypatch):
    _, headers = login(client)
    original_put = storage.put_sanitized
    def fail_put(*args):
        raise ConnectionError('synthetic failure')
    monkeypatch.setattr(storage, 'put_sanitized', fail_put)
    error(upload(client, headers), 503, 'PHOTO_STORAGE_UNAVAILABLE')
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM photos')) == 0
    monkeypatch.setattr(storage, 'put_sanitized', original_put)
    photo = upload(client, headers).json()['photoId']
    path = issue(client, headers, photo)
    with auth_runtime.sync_engine.connect() as db:
        key = db.scalar(text('SELECT object_key FROM photos WHERE id=:id'), {'id':photo})
    storage.delete(key)
    error(client.get(path), 503, 'PHOTO_STORAGE_UNAVAILABLE')


def test_cleanup_keeps_attached_and_retries_failed_deletions(client, auth_runtime, storage, monkeypatch):
    _, headers = login(client)
    unused = upload(client, headers).json()['photoId']
    used = upload(client, headers).json()['photoId']
    attach(auth_runtime, used)
    issue(client, headers, unused)
    auth_runtime.clock.advance(hours=25)
    original_delete = storage.delete
    def fail_delete(key):
        raise ConnectionError('synthetic failure')
    monkeypatch.setattr(storage, 'delete', fail_delete)
    result = asyncio.run(cleanup(auth_runtime.factory, storage, auth_runtime.clock()))
    assert result['failures'] == 1
    monkeypatch.setattr(storage, 'delete', original_delete)
    result = asyncio.run(cleanup(auth_runtime.factory, storage, auth_runtime.clock()))
    assert result['photos'] == 1
    with auth_runtime.sync_engine.connect() as db:
        assert str(db.scalar(text('SELECT id FROM photos'))) == used
        assert db.scalar(text('SELECT count(*) FROM photo_access_grants')) == 0
    assert len(list(storage.client.list_objects(storage.bucket))) == 1


def connect(rt, photo_id, item_id, user_id, **changes):
    async def run():
        async with rt.factory() as db, db.begin():
            item = await db.get(FoundItem, UUID(str(item_id)))
            user = await db.get(User, UUID(str(user_id)))
            await attach_photo(db, photo_id=UUID(str(photo_id)), item=item, user=user,
                now=rt.clock(), alt_text='테스트 물품 사진', display_order=1, **changes)
    try:
        asyncio.run(run())
        return 201, None
    except AuthError as exc:
        return exc.status, exc.code


def test_attachment_ownership_purpose_expiration_and_concurrent_reuse(client, auth_runtime):
    owner, headers = login(client)
    initial = upload(client, headers).json()['photoId']
    item = attach(auth_runtime, initial)['item']
    second_initial = upload(client, headers).json()['photoId']
    second_item = attach(auth_runtime, second_initial)['item']
    candidate = upload(client, headers).json()['photoId']
    dropoff = upload(client, headers, purpose='DROP_OFF').json()['photoId']
    assert connect(auth_runtime, dropoff, item, owner) == (400, 'INVALID_REFERENCE')
    assert connect(auth_runtime, initial, item, owner) == (409, 'PHOTO_ALREADY_ATTACHED')
    with TestClient(client.app, base_url='https://testserver') as other:
        outsider, other_headers = login(other, 'faculty-01')
        foreign_photo = upload(other, other_headers).json()['photoId']
    assert connect(auth_runtime, foreign_photo, item, owner) == (403, 'PHOTO_FORBIDDEN')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(connect, auth_runtime, candidate, target, owner) for target in (item, second_item)]
        results = [future.result(timeout=10) for future in futures]
    assert sorted(results) == [(201, None), (409, 'PHOTO_ALREADY_ATTACHED')]
    with auth_runtime.sync_engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM photo_attachments WHERE photo_id=:id'), {'id':candidate}) == 1
        assert db.scalar(text('SELECT unattached_expires_at FROM photos WHERE id=:id'), {'id':candidate}) is None
    expired = upload(client, headers).json()['photoId']
    auth_runtime.clock.advance(hours=25)
    assert connect(auth_runtime, expired, item, owner) == (400, 'INVALID_REFERENCE')


def test_cleanup_skips_photo_locked_by_attachment_writer(client, auth_runtime, storage):
    import threading
    owner, headers = login(client)
    initial = upload(client, headers).json()['photoId']
    item_id = attach(auth_runtime, initial)['item']
    candidate = upload(client, headers).json()['photoId']
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('UPDATE photos SET unattached_expires_at=:expires WHERE id=:id'),
                   dict(expires=auth_runtime.clock()+timedelta(seconds=1), id=candidate))
    locked, release = threading.Event(), threading.Event()
    async def writer():
        async with auth_runtime.factory() as db, db.begin():
            item = await db.get(FoundItem, item_id)
            user = await db.get(User, UUID(owner))
            await attach_photo(db, photo_id=UUID(candidate), item=item, user=user,
                now=auth_runtime.clock(), alt_text='사진', display_order=1)
            locked.set()
            await asyncio.to_thread(release.wait, 5)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, writer())
        try:
            assert locked.wait(3)
            result = asyncio.run(cleanup(auth_runtime.factory, storage,
                auth_runtime.clock()+timedelta(seconds=2)))
            assert result['photos'] == 0
        finally:
            release.set()
        future.result(timeout=10)
    with auth_runtime.sync_engine.connect() as db:
        key = db.scalar(text('SELECT object_key FROM photos WHERE id=:id'), {'id':candidate})
        assert db.scalar(text('SELECT count(*) FROM photo_attachments WHERE photo_id=:id'), {'id':candidate}) == 1
    assert storage.read(key)


def test_cleanup_skips_active_upload_intent(client, auth_runtime, storage, monkeypatch):
    import threading
    _, headers = login(client)
    entered, release = threading.Event(), threading.Event()
    put = storage.put_sanitized
    def blocking_put(*args):
        entered.set()
        assert release.wait(5)
        return put(*args)
    monkeypatch.setattr(storage, 'put_sanitized', blocking_put)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(upload, client, headers)
        try:
            assert entered.wait(3)
            result = asyncio.run(cleanup(auth_runtime.factory, storage,
                auth_runtime.clock()+timedelta(hours=2)))
            assert result['intents'] == 0
        finally:
            release.set()
        response = future.result(timeout=10)
    assert response.status_code == 201, response.text
    path = issue(client, headers, response.json()['photoId'])
    assert client.get(path).status_code == 200


def test_expired_unattached_and_hidden_member_admin_permissions(client, auth_runtime):
    owner, headers = login(client)
    photo = upload(client, headers).json()['photoId']
    item_id = attach(auth_runtime, photo)['item']
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('UPDATE found_items SET hidden=true WHERE id=:id'), {'id':item_id})
    with TestClient(client.app, base_url='https://testserver') as other:
        _, other_headers = login(other, 'faculty-01')
        error(other.post(f'{BASE}/photos/{photo}/access-url', headers=other_headers), 404, 'NOT_FOUND')
        _, admin_headers = login(other, 'admin-01')
        path = issue(other, admin_headers, photo)
        assert other.get(path).status_code == 200
    unused = upload(client, headers).json()['photoId']
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('UPDATE photos SET unattached_expires_at=:now WHERE id=:id'),
                   dict(now=auth_runtime.clock(), id=unused))
    error(client.post(f'{BASE}/photos/{unused}/access-url', headers=headers), 404, 'NOT_FOUND')


def test_bucket_setup_is_idempotent_and_refuses_anonymous_policy(storage):
    import json
    from service.photo_storage_setup import setup
    setup(storage)
    setup(storage)
    storage.client.set_bucket_policy(storage.bucket, json.dumps({
        'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Principal': {'AWS': ['*']},
        'Action': ['s3:GetObject'], 'Resource': [f'arn:aws:s3:::{storage.bucket}/*']}]}))
    try:
        with pytest.raises(RuntimeError):
            setup(storage)
    finally:
        storage.client.delete_bucket_policy(storage.bucket)


def test_large_object_write_avoids_abandoned_multipart_parts(storage, monkeypatch):
    def multipart_must_not_start(*args, **kwargs):
        raise AssertionError('Photo upload must use a single PUT')
    monkeypatch.setattr(storage.client, '_create_multipart_upload', multipart_must_not_start)
    content = b'x' * (6 * 1024 * 1024)
    key = storage.put_sanitized(content, 'image/jpeg')
    assert storage.read(key) == content
