"""Run migrations and tests using the existing Compose db/storage services.

docker compose exec -T backend python -m scripts.test_backend
"""
import os
from pathlib import Path
import subprocess
import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


def main():
    if not Path('/.dockerenv').exists():
        raise SystemExit('Run this command inside the backend container')
    development = make_url(os.environ['DATABASE_URL'])
    test = make_url(os.environ['TEST_DATABASE_URL']) if os.getenv('TEST_DATABASE_URL') else development.set(database='kaifind_test_backend')
    if (not test.database or not test.database.startswith('kaifind_test_')
            or (test.host, test.port, test.database) == (development.host, development.port, development.database)):
        raise SystemExit('Tests require a separate kaifind_test_* database')
    admin = test.set(drivername='postgresql', database='postgres')
    with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True) as db:
        if not db.execute('SELECT 1 FROM pg_database WHERE datname=%s', (test.database,)).fetchone():
            db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(test.database)))
    env = dict(os.environ)
    env['TEST_DATABASE_URL'] = test.set(drivername='postgresql').render_as_string(hide_password=False)
    env['DATABASE_URL'] = env['TEST_DATABASE_URL']
    for target, source in (
        ('TEST_MINIO_ENDPOINT', 'MINIO_ENDPOINT'), ('TEST_MINIO_ACCESS_KEY', 'MINIO_ACCESS_KEY'),
        ('TEST_MINIO_SECRET_KEY', 'MINIO_SECRET_KEY'), ('TEST_MINIO_SECURE', 'MINIO_SECURE'),
    ):
        if not env.get(target):
            if not env.get(source):
                raise SystemExit(f'Set {source} in the backend environment')
            env[target] = env[source]
    # No credentials in stdout or command arguments; child processes inherit env.
    print('Preparing the isolated test database in the existing db service', flush=True)
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], env=env, check=True)
    args = sys.argv[1:] or ['tests', '-q']
    result = subprocess.run([sys.executable, '-m', 'pytest', *args], env=env)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
