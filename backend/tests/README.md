# 테스트 실행

spaCy·WordNet v2: requirements.txt 설치 후 기존 backend에서 `python -m scripts.prepare_keyword_resources`를 실행해야 키워드 테스트를 실행할 수 있다. `test_wordnet_keywords.py`는 실제 영어 모델·WordNet으로 미등록어·표제어·명사구·동의어 일치·상위어 오탐 방지·부정·프로필 분리를 검증한다. 추출 테스트는 번역 모델이 없어도 가능하지만 NLP 자원은 필요하다. 자원이 없을 때 조용히 구 사전으로 fallback하지 않는다.

번역 런타임: `test_text_analysis.py`는 언어 fallback·키워드·타임아웃/취소 제어를, `test_text_analysis_lifespan.py`는 비활성/실패/상주 상태를 검증한다. `test_translation_runtime_real.py` 및 실제 lifespan 검증은 모델 준비 후 `RUN_REAL_TEXT_ANALYSIS_TESTS=true`를 컨테이너 명령에 전달해 실행한다. 일반 HTTP 테스트는 모델을 비활성화하며, 실제 모델 테스트가 skip된 결과는 모델 검증 성공이 아니다. 명령과 합성 품질 평가 방법은 [런타임 안내](../docs/design/translation-runtime.md)를 참고한다.

Python·pip·pytest·Alembic은 기존 Compose의 backend 컨테이너 안에서 실행한다.
프로젝트 루트 `.env`를 설정하고 기존 `db`, `storage`, `backend` 서비스를 실행한 상태에서:

```sh
docker compose exec -T backend python -m scripts.test_backend
```

이 명령은 기존 db 서비스 안의 별도 `kaifind_test_backend` 데이터베이스를 준비하고,
해당 DB에 마이그레이션을 적용한 뒤 전체 테스트를 실행한다. PostgreSQL 데이터베이스 생성 권한이
필요하며, 이미 준비된 테스트 DB는 재사용한다. 테스트 DB와 개발 DB는 분리한다.
MinIO는 기존 storage 서비스를 사용하며 테스트마다 `kaifind-test-<임의 값>` 버킷을 생성·삭제한다.
새 서비스 컨테이너나 호스트 가상환경을 만들지 않는다.

일부 테스트만 실행할 수도 있다.

```sh
docker compose exec -T backend python -m scripts.test_backend tests/test_photo_contract.py -q
```

기본 테스트 DB를 바꾸려면 `docker compose exec -e TEST_DATABASE_URL=...`로
전용 DB 주소를 전달한다. DB 이름이 `kaifind_test_`로 시작하지 않으면 통합 테스트를 거부한다.
개발·운영 DB를 지정하지 않는다. MinIO의 `TEST_MINIO_*` 설정은 별도 지정하지 않으면
backend의 `MINIO_*` 환경변수를 사용한다. 자격증명은 로그·코드에 기록하지 않는다.

## 인증·관리자·스키마

- `test_protected_http.py`: 실세션으로 본문 없는 POST/DELETE의 인증·CSRF·Origin, 불필요 본문 거부, 기존 JSON 검증과 OpenAPI를 검증한다. 기능 API 대신 테스트 전용 라우트를 사용한다.
- `test_matching_models.py`: 비동기 상태·후보 응답·완전성·KST·쿼리 계약과 비공개 필드 차단을 검증한다.
- `test_matching_lock.py`: 기존 db의 전용 테스트 DB에서 카테고리 잠금의 유지·커밋/롤백 해제·역순 다중 잠금을 검증한다. 등록/수거 서비스의 실제 잠금 연동은 후속 검증이다.

- `test_auth_models.py`: DB 없이 요청 필드·타입·추가 필드 거부와 응답 직렬화를 검증한다.
- `test_auth_params.py`: 파라미터 누락 시 최종 인증 오류, OpenAPI 파라미터와 204 응답을 검증한다.
- `test_auth_contract.py`: 실제 라우터로 로그인·CSRF·쿠키·로그아웃·언어별 오류 계약을 검증한다.
- `test_auth_service.py`: PostgreSQL에서 만료 경계·활동 갱신·권한 유지·암호화·롤백·동시 로그인·세션 폐기 경합·IP별 동시 요청 제한을 검증한다.
- `test_schema.py`: PostgreSQL 스키마 제약을 검증하며 테스트별 트랜잭션을 롤백한다.
- `test_matching_schema.py`: 텍스트 버전·프로필 불변성·분석 상태·후보 FK·lease/종료 제약·generation·삭제 취소와 SKIP LOCKED를 검증한다.
- `test_matching_migration.py`: 기존 db 서비스에 별도 `kaifind_test_matching_migration_*` DB를 생성해 0005→0006 데이터 이행·다운그레이드·재적용을 검증하고 해당 임시 DB만 삭제한다. CREATEDB 권한이 필요하다.
- `test_admin_models.py`: DB 없이 DTO·감사 허용목록·OpenAPI를 검증한다.
- `test_admin_contract.py`: HTTP·DB로 권한 즉시 반영, 쓰기 보안, 기준정보 중복, 신고 숨김,
  분쟁 검토, 근거 삭제 후 제한 해제, 통계·감사 필터·감사 실패 롤백·동시 변경을 검증한다.

Auth 테스트는 각 테스트 시작 시 `users`, `sessions`, `auth_login_rates`와 연결 데이터를 TRUNCATE한다.
관리자·사진 fixture는 기준정보·감사·사진 intent도 TRUNCATE하므로 반드시 전용 테스트 DB를 사용한다.
동일 DB에서 병렬 pytest 실행은 지원하지 않는다. DB 주소가 없어서 skip된 결과는 통합 검증 성공이 아니다.

테스트 clock은 `2026-11-03T10:00:00+09:00`으로 고정하며 직접 전진시킨다.
합성 계정·암호화 키·허용 origin은 fixture에서 주입하고 실제 핸들러·DB를 대체하지 않는다.

## 사진 API

`test_photo_images.py`와 `test_photo_storage.py`는 DB 없이 이미지 정제·GPS 제거·회전·포맷·크기·픽셀 제한,
SDK 연결 해제·설정·OpenAPI·Uvicorn 토큰 마스킹을 검증한다.
`test_photo_contract.py`는 실제 PostgreSQL과 MinIO에서 API·인가·감사 커밋·업로드 보상·정리·동시 연결을 검증한다.
사진 테스트의 임시 버킷에는 테스트 산출물만 저장하고 fixture 종료 시 해당 버킷을 삭제한다.
DB 또는 MinIO 설정이 없으면 해당 통합 테스트는 skip된다.
실제 모바일 네트워크의 업로드 5초 목표, 물품 등록 HTTP 전체 흐름, 연결 사진의 보존 기간 삭제는
현재 검증 범위에 포함하지 않는다.

## 프로필 API

- `test_profile_models.py`: 언어 trim·ko/en 검증, 필수 필드·추가 필드 거부 및 OpenAPI 계약을 검증한다.
- `test_profile_contract.py`: MEMBER·ADMIN 본인 조회, 언어 변경·재로그인 유지·계정 간 격리,
  인증·세션 만료·CSRF·Origin·JSON 오류와 실패 시 프로필 보존, 응답 헤더를 검증한다.

```sh
docker compose exec -T backend python -m scripts.test_backend tests/test_profile_models.py tests/test_profile_contract.py -q
```

## 공개 기준정보 API

- `test_reference_models.py`: 집계 필드 직렬화·음수 거부, 쿼리 추가 필드 거부, 공개 OpenAPI를 검증한다.
- `test_reference_contract.py`: 실제 PostgreSQL에서 활성 목록·빈 목록·정렬, 관리자 변경 반영,
  회원·비회원·잘못되거나 만료된 쿠키의 공개 접근, 최신 보관 건물별 집계와 제외 조건,
  쿼리 오류·언어·DB 오류 은닉·응답 헤더를 검증한다. MinIO는 사용하지 않는다.

```sh
docker compose exec -T backend python -m scripts.test_backend tests/test_reference_models.py tests/test_reference_contract.py -q
```

목록은 생성시각 내림차순·동률 ID 내림차순이다. `postedCount`는 요청 시 0건도 포함하고
생략 또는 false이면 응답 필드에서 제외한다. 집계는 물품별 최대 revision_no를 먼저 선택한 후
DROP_OFF·POSTED·비숨김·비삭제 조건을 적용한다. 실제 대규모 데이터 성능은 별도 검증 대상이다.

## 메시지 API

`test_message_contract.py`는 대화 생성·재사용·동시 생성 유일성, 참여자 권한과 관리자 접근 차단,
메시지 전송·공백 정리·연락처 포함 본문 허용, 인증·CSRF·쿼리 검증, 페이지 정렬,
숨김 이후 기존 대화 사용, 물품 종료·삭제와 전송 경합의 즉시 삭제를 검증한다.

```sh
docker compose exec -T -w /app backend python -m scripts.test_backend tests/test_message_contract.py -q
```

테스트 DB의 마이그레이션 이력이 현재 소스와 다르면 기존 DB 이력을 덮어쓰지 않고
별도 `kaifind_test_*` DB를 `TEST_DATABASE_URL`로 지정한다.
실제 부하와 폴링 주기, 클라이언트 HTML 렌더링은 검증 범위 밖이다.

## 분쟁 API

`test_dispute_contract.py`는 작성자 접수·작성자/관리자 목록 권한, 사유·페이지 검증,
숨김·삭제·미수거 처리, 관리자 검토·수거 제한 연동, 보존 만료 상속,
취소·재수거 이력과 동률 정렬, 동시 접수 유일성, 취소 트랜잭션과 접수 경합을 검증한다.
수거 취소 API는 아직 미구현이므로 경합 테스트는 동일한 물품 잠금을 사용하는 DB
트랜잭션으로 취소를 재현한다. 수거 HTTP 전체 흐름과 대규모 조회 성능은 미검증이다.

```sh
docker compose exec -T -w /app backend python -m scripts.test_backend tests/test_dispute_contract.py tests/test_admin_contract.py tests/test_schema.py -q
```
