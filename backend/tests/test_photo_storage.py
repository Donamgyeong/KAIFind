"""Storage boundaries without a running MinIO server."""

from unittest.mock import Mock

import pytest
from minio import Minio
from minio.error import S3Error

from library.photo_storage import PhotoStorage, StorageSettings


def test_settings_require_credentials_and_default_to_tls(monkeypatch):
    for key in ('MINIO_ENDPOINT', 'MINIO_ACCESS_KEY', 'MINIO_SECRET_KEY',
                'MINIO_BUCKET', 'MINIO_SECURE'):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError):
        StorageSettings.from_env()
    monkeypatch.setenv('MINIO_ENDPOINT', 'localhost:9000')
    monkeypatch.setenv('MINIO_ACCESS_KEY', 'test-access')
    monkeypatch.setenv('MINIO_SECRET_KEY', 'test-secret')
    settings = StorageSettings.from_env()
    assert settings.secure is True
    assert 'test-secret' not in repr(settings)
    monkeypatch.setenv('MINIO_SECURE', 'false')
    assert StorageSettings.from_env().secure is False
    monkeypatch.setenv('MINIO_SECURE', 'typo')
    with pytest.raises(ValueError):
        StorageSettings.from_env()


def test_real_sdk_constructs_without_connecting():
    storage = PhotoStorage(StorageSettings('localhost:9000', 'key', 'secret'))
    assert isinstance(storage.client, Minio)


def test_upload_uses_unique_keys_and_preserves_bytes():
    client = Mock(spec=Minio)
    storage = PhotoStorage(StorageSettings('localhost:9000', 'key', 'secret'), client)
    key = storage.put_sanitized(b'sanitized-image', 'image/jpeg')
    args, kwargs = client.put_object.call_args
    assert args[0:2] == ('kaifind-photos', key)
    assert args[2].read() == b'sanitized-image'
    assert args[3] == len(b'sanitized-image')
    assert kwargs == {'content_type': 'image/jpeg', 'part_size': 5 * 1024 * 1024}
    assert key.endswith('.jpg')
    assert storage.put_sanitized(b'sanitized-image', 'image/jpeg') != key
    for content, mime in ((b'', 'image/jpeg'), (b'bytes', 'text/html')):
        with pytest.raises(ValueError):
            storage.put_sanitized(content, mime)


@pytest.mark.parametrize('fail', [False, True])
def test_download_always_releases_connection(fail):
    client = Mock(spec=Minio)
    response = client.get_object.return_value
    storage = PhotoStorage(StorageSettings('localhost:9000', 'key', 'secret'), client)
    if fail:
        response.read.side_effect = OSError('interrupted')
        with pytest.raises(OSError):
            storage.read('photos/example.jpg')
    else:
        response.read.return_value = b'image'
        assert storage.read('photos/example.jpg') == b'image'
    response.close.assert_called_once()
    response.release_conn.assert_called_once()


def test_missing_objects_propagate_to_service():
    client = Mock(spec=Minio)
    client.get_object.side_effect = S3Error(
        'NoSuchKey', 'Missing', 'resource', 'request', 'host', None)
    storage = PhotoStorage(StorageSettings('localhost:9000', 'key', 'secret'), client)
    with pytest.raises(S3Error):
        storage.read('photos/missing.jpg')
    storage.delete('photos/example.jpg')
    client.remove_object.assert_called_once_with('kaifind-photos', 'photos/example.jpg')
