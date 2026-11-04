"""Explicit deploy-time bucket setup; API workers never create/publicize buckets."""
import time

from minio.error import S3Error
from urllib3.exceptions import HTTPError

from library.photo_storage import photo_storage


def setup(storage):
    if not storage.client.bucket_exists(storage.bucket):
        try:
            storage.client.make_bucket(storage.bucket)
        except S3Error as exc:
            if exc.code != 'BucketAlreadyOwnedByYou':
                raise
    try:
        storage.client.get_bucket_policy(storage.bucket)
    except S3Error as exc:
        if exc.code == 'NoSuchBucketPolicy':
            return
        raise
    raise RuntimeError('Photo bucket has a policy; verify and remove anonymous access before deployment')


def main():
    storage = photo_storage()
    for attempt in range(20):
        try:
            setup(storage)
            print('Private photo bucket ready')
            return
        except (HTTPError, ConnectionError, TimeoutError):
            if attempt == 19:
                raise RuntimeError('Photo storage is unavailable') from None
            time.sleep(1)


if __name__ == '__main__':
    main()
