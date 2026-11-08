# DB 모델·마이그레이션 사용법

2026-11-08: [3단계 분석 워커](../design/text-analysis-worker.md)와 revision `20261108_0007`을 추가했다. 새 revision은 감사 action의 TEXT_ANALYSIS_RETRIED와 metadata의 eventId 허용 목록만 확장한다. 기존 기록을 변경하지 않는다. 재시도 감사가 있으면 downgrade는 이력 보존을 위해 거절한다. 아래 0006 설명은 도입 당시 이력이며 분석 소비자는 이제 구현됐다. 후보 재평가 소비자·알림·수거 연결은 후속 단계다.

2026-11-07: 개발 DB는 저장소에서 빠진 `20261106_0005`를 가리키고 있었다. Git 이력 `79af37a`의 원본 마이그레이션을 복원하고 새 revision `20261107_0006`을 연결했다. 번역·키워드 기반 비동기 매칭의 [상세 DB 설계](../design/translation-keyword-db-schema.md)를 DB 모델·마이그레이션에 반영했다. 과거 embedding-db-schema.md 링크는 유효하지 않다.

## 2026-11-07 번역·키워드 DB 기반

- `model/matching.py`: 분석 프로필·정책·활성 정책·양쪽 분석 결과·generation 기반 재평가 작업, 총 6개 테이블 추가.
- `model/entities.py`, `model/indexes.py`: text_version, 후보 판정 버전·복합 FK·공통 키워드·legacy_evidence, outbox 실패/취소/lease 제약, 작업·날짜 인덱스 추가.
- `20261107_0006`: description_version 카운터를 유지해 text_version으로 변경. 제목/설명 변경 트리거, 프로필·정책 불변 트리거, READY 결과/입력 정체성 보호, 논리 삭제 시 분석·재평가 작업 제거, 분석 삭제 시 대기 outbox 취소 구현.
- 기존 의미 점수·버전은 후보의 legacy_evidence에 보존한다. 후보 ID·최초 시각·최초 알림을 유지하고 건물 근거 없는 이전 후보는 재평가 전까지 비활성화한다.
- 기존 outbox lease를 해제하므로 배포 시 소비자를 멈춘 뒤 마이그레이션하고 호환 소비자로 재개해야 한다. 현재 번역·매칭 소비자는 아직 미구현이다.

신규 프로필의 실제 모델 revision·라이브러리 버전은 런타임 호환성 검증 후 등록한다. 마이그레이션은 가짜 프로필이나 활성 정책을 넣지 않는다. API/워커의 작업 생성, lease 소유권 조건부 저장, 재시도·재평가, 카테고리 advisory lock, 수거 최신성 확인, 알림 연동·정리 배치는 후속 구현이다. DB 필드·제약만으로 이 서비스 계약까지 완료된 것은 아니다.

검증은 기존 backend 컨테이너의 `/app`에서 기존 db 안의 별도 `kaifind_test_matching_schema_20261107` DB로 수행했다. 전체 upgrade→downgrade base→upgrade와 `alembic check`를 통과했다. 별도 임시 DB의 이행 테스트는 기존 의미 판정·버전·알림 시각 보존 및 0005↔0006 왕복을 확인한다. 개발 DB에는 downgrade를 실행하지 않는다.

2026-11-07 적용 결과: 기존 개발 DB를 `20261106_0005`에서 `20261107_0006 (head)`으로 upgrade했고 `alembic check`에서 차이가 없었다. 적용 전후 기존 테이블별 행 수, 원본 텍스트 버전 카운터, 후보 ID·최초 매칭/알림 시각 보존을 확인했다. 전체 테스트 328개와 이후 추가한 기존 데이터 이행·ORM 버전 조회 테스트 각 1개, 총 330개가 통과했다. 번역 품질·처리량·워커/수거 최신성 경합은 아직 검증하지 않았다.

현재 개발·테스트 명령은 [상위 개발 안내](../../README.md)를 따른다. 아래 과거 호스트 Python 예시 대신 실행 중인 backend 컨테이너의 /app에서 `docker compose exec -T backend ...`로 실행한다.

2026-11-02 구현: SQLAlchemy 2 ORM 27개 테이블, PostgreSQL 17에서 검증한 Alembic 초기 revision `20261102_0001`.

- 모델: `model/entities.py`, 공통 Base: `model/base.py`, 인덱스: `model/indexes.py`
- 비동기 연결/세션 의존성: `library/database.py`의 `get_session`
- 마이그레이션: `migrations/versions/20261102_0001_initial_kaifind_schema.py`
- 통합 검증: `tests/test_schema.py`

2026-11-03: Auth 로그인 제한용 `auth_login_rates` 테이블을 추가했다. Auth 변경 revision은 `20261103_0002`이며 기존 DB에도 `alembic upgrade head`가 필요하다.

## 연결 설정

`DATABASE_URL` 또는 `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`를 환경변수로 전달한다. 후자는 `POSTGRES_HOST` 기본 localhost, `POSTGRES_PORT` 기본 5432다. `.env.example`은 참고용이며 애플리케이션이 `.env`를 자동으로 읽지는 않는다. 비밀번호에 특수문자가 있으면 URL 인코딩을 적용하거나 개별 POSTGRES 변수를 사용한다.

호스트에서 PostgreSQL 포워딩 포트에 연결할 때는 localhost, Compose backend에서 연결할 때는 서비스 이름 db를 사용한다. 연결 설정과 엔진은 지연 생성되며 모듈 import나 앱 시작만으로 테이블을 생성하지 않는다. 요청 세션의 commit/rollback은 서비스 트랜잭션에서 명시적으로 처리한다.

호스트에서 환경변수를 설정한 뒤:

```sh
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

현재 저장소의 상위 `.env`와 실행 중인 Compose backend/db를 사용하는 경우, backend 디렉터리에서:

```sh
set -a
source ../.env
set +a
export POSTGRES_HOST=db
docker exec -e POSTGRES_USER -e POSTGRES_PASSWORD -e POSTGRES_DB -e POSTGRES_HOST backend python -m alembic upgrade head
```

실행 중인 backend 서비스 자체에 DB 설정을 계속 제공하려면 배포 환경의 환경변수에도 같은 설정을 전달해야 한다. 위 docker exec의 환경변수는 해당 명령에만 적용된다. Auth API의 DB 호출을 구현했다.

## 검증 방법

기존 데이터가 없는 별도 `kaifind_test_*` DB에 마이그레이션을 적용하고 그 주소를 TEST_DATABASE_URL로 전달한다.

```sh
DATABASE_URL="$TEST_DATABASE_URL" python -m alembic upgrade head
python -m pytest -q tests/test_schema.py
DATABASE_URL="$TEST_DATABASE_URL" python -m alembic downgrade base
DATABASE_URL="$TEST_DATABASE_URL" python -m alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" python -m alembic check
```

테스트는 각 테스트의 데이터를 rollback한다. 임시 DB 생성/제거는 실행자가 담당한다. downgrade는 해당 스키마의 데이터를 제거하므로 검증용 DB에서만 왕복 검증한다. 초기 migration은 현재 모델의 create_all을 호출하지 않고 고정된 DDL을 포함한다.

## DB가 보장하는 규칙

PK/FK, enum CHECK, 상태·종료 시각 정합성, 위치 형태, 활성 수거 유일성, OPEN 신고/분쟁 중복 제한, 메일 슬롯 유일성, 후보·알림 중복 키, 사진 목적/소유권/물품·위치 연결, bounded 문자열 공백 검증을 포함한다.

PostgreSQL 트리거는 다음을 추가 보장한다.

- 카테고리 민감 속성 불변, 사진/과거 위치의 민감 라벨 하향 금지와 카테고리 변경 시 라벨 전파
- 사진 연결의 물품·사진·위치 정체성 불변, 위치 버전 내용 불변
- 종료 신고 private details 삭제와 OPEN 여부의 지연 제약 검사. OPEN 신고와 private 행은 같은 트랜잭션에서 생성해야 한다.
- 최초 종료 시각 변경 및 신고 재개방 금지
- 물품 종료/논리 삭제 시 대화·메시지 삭제, 논리 삭제 시 후보 삭제
- 대화/메시지 쓰기 시 물품 행 잠금·상태 검사, 메시지 발신자가 대화 참여자인지 검사
- 신고 종료 시 대기 이메일 항목 CANCELLED 처리

ORM에서 User/FoundItem/LostReport를 수정하면 version 컬럼으로 낙관적 잠금이 적용된다. Core update·직접 SQL은 ORM 잠금을 우회하므로 서비스에서 버전 조건/행 잠금과 version 증가를 명시해야 한다.

## 서비스·운영 구현에 남은 내용

이번 변경은 DB 기반 작업이며 63개 API와 배치/워커 구현을 포함하지 않는다. 수거 상태와 수거 기록의 원자적 연동·최신 매칭·모든 관련 신고 종료·감사 및 outbox 생성은 서비스가 같은 트랜잭션에서 처리해야 한다. 사진 최소 1~5장, 가능한 건물 최소 1개, 미래 날짜, 서버 인가·CSRF·연락처 검출·GPS 제거·사진 바이트 전달 감사도 해당 처리 경로에서 검증한다.

알림 worker, 슬롯 예약·재시도 날짜 이월, purge_after 계산·정리 배치, 객체 스토리지 삭제, 백업 삭제 재적용, 감사 metadata 값별 허용 형식·상태값 검증, 감사 append-only 전용 DB 권한은 후속 구현이다. 감사 CHECK는 이벤트/대상 enum·주체 형태·metadata 키 허용목록까지만 검사한다. 민감 데이터 원문 복제를 금지하는 것은 큐/로그 작성 경로에서도 지켜야 한다.

수거 기록 삭제 후 조회·취소 정책은 미정이다. 제한 근거 삭제 후 해제 충돌은 ADS-04에서 해제 시 disputeId 생략을 허용하는 설계로 조정했다. 명시적 해제까지 유지·해제 절차는 SRS 미정 사항의 설계 제안이며 해당 API·서비스는 아직 미구현이다. collections.item_id와 audit/이벤트 식별자에는 독립 보존을 위해 물리 FK를 두지 않았다. collection_restrictions.source_dispute_id는 ON DELETE SET NULL로 제한 상태를 보존한다. 전체 미정 정책은 [스키마 초안](README.md)의 10절을 따른다.

## 이번 적용 결과

2026-11-02 실행 중인 Compose PostgreSQL 개발 DB에 `upgrade head`를 적용했다. 현재 revision은 `20261102_0001 (head)`이며 `alembic check`에서 신규 변경이 검출되지 않았다.

별도 임시 PostgreSQL DB에서 upgrade→downgrade base→upgrade 왕복, 스키마 차이 검사, 통합 테스트 11개를 통과했다. 테스트는 수거 유일성·취소 후 재수거, 이메일 슬롯, 신고 종료 시 private 삭제·재개방 차단, 메시지 참여자 검사·종료 삭제, 사진 민감 라벨 유지·목적 검사, 위치 이력 불변, 수거 독립 보존, ORM version 충돌을 검증한다. 임시 DB는 검증 후 제거했다. 다중 요청 부하·외부 이메일 전송·백업 복구는 검증하지 않았다.

## 2026-11-03 관리자 API 추가

최신 revision은 `20261103_0003`이다. 건물 코드와 각 언어별 카테고리 이름에
`lower(btrim(...))` 고유 인덱스를 추가하여 동시 생성·이름 변경 중복을 방지한다.
기존 데이터에 정규화 중복이 있으면 마이그레이션은 실패하며 자동 병합하지 않는다.
개발·운영 DB 적용 전 중복을 정리해야 한다.

Admin API·회원 게시물 신고·변경 감사 서비스는 구현했다.
기존 비관리자 업무 API 및 보존 정리 배치·감사 전용 DB 권한 설정은 별도 작업이다.
