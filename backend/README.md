# KAIFind backend 개발

번역·키워드 모델은 앱 startup에서 기본 활성화된다. 최초 실행/새 이미지 설치 후 기존 backend 컨테이너에서 `python -m scripts.prepare_translation_model`과 `python -m scripts.prepare_keyword_resources`로 로컬 번역 모델·WordNet을 준비한다. spaCy 영어 모델은 requirements.txt로 설치한다. 누락 시 startup은 실패하며 준비 후 backend를 재시작한다. 설치·환경설정·평가와 후속 연결 범위는 [런타임 안내](docs/design/translation-runtime.md)와 [spaCy·WordNet 설계](docs/design/spacy-wordnet-keywords.md)를 참고한다. 일반 API 테스트는 번역 모델을 비활성화하고 실제 모델 테스트는 별도 명시 실행한다.

3단계 분석 워커: 모델 준비 후 기존 backend의 `/app`에서 `python -m alembic upgrade head`, `python -m scripts.manage_text_analysis initialize`를 수행하고 backend를 재시작한다. 활성 정책 누락·모델 불일치 시 startup은 실패한다. 초기화·복구·재시도 명령과 4단계 호출 계약은 [분석 작업 안내](docs/design/text-analysis-worker.md)를 따른다.

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

환경변수는 backend 상위 프로젝트 루트 `.env` 한 곳에서 관리한다.
새 변수도 이 파일에 추가하고, 비밀정보 없는 예시는 같은 루트 `example.env`에 반영한다.
backend 안에는 별도 환경변수 파일을 만들지 않는다. Compose가 backend에 전달한다.
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

## 알림·이메일

기존 backend 프로세스에서 매칭 최초 후보와 수거/만료 outbox를 인앱 알림·이메일 대기로 변환한다.
수거·만료는 DB 상태 변경과 함께 이벤트를 기록하며 해당 도메인 HTTP API·만료 스케줄러 구현을 대체하지 않는다.
키워드 등록 이벤트 생산자와 구독 API는 revision 20261109_0010에 연결했다.

알림 환경변수는 상위 프로젝트 `.env`에 통합되어 있으며 예시는 같은 루트 `example.env`를 참고한다.
값을 변경한 뒤
`docker compose up -d --no-deps backend`로 기존 backend에 반영한다.
`NOTIFICATION_EMAIL_ENABLED=false`가 기본이다. true여도 현재 제공자는 **mock만 지원**하며 외부 메일을 보내지 않는다.
mock 수신 확인은 `mock_email_receipts`와 `email_deliveries`에 저장하고 본문·수신 주소는 복제하지 않는다.

일일 한도는 `NOTIFICATION_EMAIL_DAILY_LIMIT`(기본 20), digest 시각은
`NOTIFICATION_EMAIL_DIGEST_TIME`(기본 20:00 KST)이다. 개별 최대 한도는 일일 한도-1이다.
초과분은 digest로 묶고 마감 이후 초과분은 다음 날로 이월한다. 빈 digest는 보내지 않는다.
한도와 시각 변경은 재시작 이후 새로 확정되는 다음 KST 날짜 정책부터 적용한다.
전송 전역 중지는 대기를 보존하며 사용자 수신 거부는 해당 항목을 취소한다.

새 revision `20261109_0009` 적용 후 사용한다.

```sh
docker compose exec -T -w /app backend python -m alembic upgrade head
docker compose exec -T -w /app backend python -m scripts.manage_notifications failures
docker compose exec -T -w /app backend python -m scripts.manage_notifications retry <delivery-uuid>
docker compose exec -T -w /app backend python -m scripts.manage_notifications retry-event <event-uuid>
```

UNKNOWN은 결과 확인 대상으로 남기며 수동 retry로 강제 재발송하지 않는다.
기존 DB·MinIO 볼륨을 삭제하거나 별도 서비스 컨테이너를 만들 필요는 없다.

## 키워드 구독

revision `20261109_0010`에서 KEYWORD-01~03과 습득물 INSERT→등록 스냅샷→키워드 알림을 연결했다.
구독과 공개 제목·설명을 같은 번역·분석기로 처리한 후 구독의 모든 단어 특징이 포함될 때 알린다.
명사구와 WordNet 동의어 특징은 필수 조건에서 제외하며 기존 분실 신고 매칭은 유지한다.
상세 계약·경합·프로필 변경·한계는 [구현 설계](docs/design/keyword-subscriptions.md)를 따른다.

`TEXT_ANALYSIS_ENABLED=true`와 준비된 활성 프로필이 필요하다. 구독 생성은 분석 성공 후201이며,
모델 비활성·busy·timeout은503과 Retry-After: 5다. 습득물 등록 HTTP API는 아직 별도 구현 영역이다.
DB 등록 이벤트는 분석 비활성 중에도 저장되며 등록 후 수정·늦게 만든 구독으로 소급 통지하지 않는다.
기존 알림 워커가 분석 활성 여부와 무관하게 매시간 보존 정리를 실행한다.
미분석 원문은30일 경과 후 다음 정리에서 삭제하고, 완료7일 후 분석 특징을 정리한다.
이미 생성된 인앱 알림과 중복 억제 표식은 유지한다.

```sh
docker compose exec -T -w /app backend python -m scripts.manage_keyword_subscriptions failures
docker compose exec -T -w /app backend python -m scripts.manage_keyword_subscriptions retry <event-uuid>
docker compose exec -T -w /app backend python -m scripts.manage_keyword_subscriptions cleanup
```

다른 프로필로 전환하기 전에 이전 프로필의 미완료·실패 등록 이벤트를 처리해야 한다.
DB 트리거가 미처리 이벤트가 있는 프로필 교체를 거부한다. 외부 이메일은 여전히 mock만 지원한다.

## DB 일일 백업

매일 04:00 KST에 기존 backend에서 `pg_dump -Fc`를 실행해 기존 MinIO의 비공개
`kaifind-db-backups` 버킷에 저장하고, 성공 이후 7일 지난 백업을 정리한다.
정책은 상위 프로젝트 `.env`의 `BACKUP_*` 환경변수로 조정하며 예시는 같은 루트 `example.env`를 참고한다.
revision `20261109_0011` 적용과 PostgreSQL 17 클라이언트를 포함한 이미지 빌드 후 사용한다.
설정·적용 순서·수동 실행·복구 절차 및 만료 검사 연동의 미완료 범위는
[백업 운영 안내](docs/design/database-backups.md)를 따른다.
