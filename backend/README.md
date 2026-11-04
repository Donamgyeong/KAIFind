# KAIFind backend 개발

기존 상위 `docker-compose.yaml`의 세 서비스를 함께 사용한다.

| 서비스 | 역할 | 컨테이너 내부 주소 |
| --- | --- | --- |
| backend | FastAPI, 개발 명령, 테스트 | `/app`, 포트 8000 |
| db | PostgreSQL | `db:5432` |
| storage | 비공개 사진 저장소 MinIO | `storage:9000` |

`backend` 디렉터리에서 아래 명령을 실행하면 Compose가 상위 설정을 찾는다.
소스는 `/app`에 바인드 마운트되어 편집 내용이 바로 반영된다.
Python·pip·pytest·Alembic은 호스트 가상환경 대신 backend 안에서 실행한다.

```sh
docker compose up -d --build
docker compose exec backend sh
# 컨테이너 안에서: python ..., python -m scripts.test_backend
```

환경변수는 프로젝트 루트 `.env`에 설정한다. Compose가 backend에 전달한다.
로컬 MinIO 접근 키를 생략하면 기존 `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`를 사용한다.
운영 환경에는 전용 접근 키를 설정한다. Auth 사용 시 `AUTH_ENCRYPTION_KEY`가 필요하며,
목업 로그인은 `APP_ENV=local`, `MOCK_AUTH_ENABLED=true`를 명시해야 활성화된다.
자세한 설정은 [Auth 문서](docs/api/AUTH-IMPLEMENTATION.md), [사진 문서](docs/MINIO.md)를 참고한다.

개발 DB 마이그레이션과 사진 버킷 초기화는 필요한 경우에 실행한다.

```sh
docker compose exec -T backend python -m alembic upgrade head
docker compose exec -T backend python -m service.photo_storage_setup
```

라이브러리는 먼저 `requirements.txt`에 버전을 기록한 뒤 설치한다.
컨테이너에만 설치한 채로 끝내지 않는다.

```sh
docker compose exec -T backend python -m pip install -r requirements.txt
docker compose exec -T backend python -m pip check
# requirements.txt 또는 Dockerfile 변경 후 이미지 재생성
docker compose up -d --build backend
```

전체 테스트는 기존 db 안에 별도 `kaifind_test_backend` DB를 준비하고, 해당 DB에만
마이그레이션을 적용한다. 기존 storage 안의 임의 이름 테스트 버킷은 테스트 종료 시 삭제한다.
별도 서비스 컨테이너를 만들지 않으며 개발 DB·사진 버킷을 테스트에 사용하지 않는다.

```sh
docker compose exec -T backend python -m scripts.test_backend
# 일부 테스트만 실행
docker compose exec -T backend python -m scripts.test_backend tests/test_photo_contract.py -q
```

테스트 DB 생성에는 PostgreSQL `CREATEDB` 권한이 필요하다. 생성 권한이 없다면 미리 준비한
전용 `kaifind_test_*` DB의 `TEST_DATABASE_URL`을 전달한다. 자세한 범위는 [테스트 문서](tests/README.md)를 참고한다.

DB와 MinIO는 각각 `db-data`, `storage-data` 볼륨을 사용한다. 개발을 마칠 때는
`docker compose stop`을 사용하고, 데이터를 삭제하는 `docker compose down -v`는 실행하지 않는다.
