# 번역·키워드 매칭 DB 설계

작성일: 2026-11-07 (KST). 상태: DB 모델·마이그레이션 구현. 서비스·워커는 미구현이다. 적용·검증 현황은 [DB 구현 안내](../db/IMPLEMENTATION.md)를 따른다.

상위 흐름은 [전체 구조](translation-keyword-matching.md)를 따른다. 기존 PostgreSQL과 outbox를 사용하며 신규 DB 서비스·확장은 필요하지 않다. 아래 timestamp는 모두 timestamptz다.

## 1. 테이블 관계

```text
text_analysis_profiles ← matching_policies ← matching_runtime(singleton)
         ↑
found_items → found_item_text_features ← match_candidates → lost_report_text_features ← lost_reports
                    ↑                           ↑                     ↑
              분석 outbox                match_evaluation_jobs     분석 outbox
```

분석 행은 실제 원본 FK를 가진 두 테이블로 분리한다. 다형적 ID만으로 참조 무결성을 대체하지 않는다. 분석은 버전별 행으로 저장하며 기존 후보의 최초 발생·알림 이력은 유지한다.

## 2. 원본 테이블 확장

found_items와 lost_reports에 `text_version bigint NOT NULL DEFAULT 1 CHECK (text_version > 0)`을 추가한다.

- found_items: title 또는 description이 `IS DISTINCT FROM`으로 변경되면 BEFORE UPDATE 트리거가 OLD.text_version + 1을 설정한다.
- lost_reports: description 변경 시 같은 방식으로 증가한다.
- 입력 불변 시 NEW.text_version을 OLD 값으로 고정하여 호출자가 버전을 임의 변경하지 못하게 한다.
- private details·건물·날짜만 바뀌면 text_version은 유지한다.
- 기존 version은 별도로 증가해야 한다. ORM 이외 Core/직접 SQL 경로도 version 증가와 충돌 검사를 수행한다.

원본 변경·분석 PENDING 행·작업 생성은 서비스의 같은 트랜잭션이다. 트리거는 텍스트 버전만 보장하며 작업 생성은 보장하지 않는다. 정합성 복구 배치가 현재 버전/활성 프로필에 분석·작업이 없는 원본을 보완한다. 입력 해시는 제목/설명 경계가 있는 canonical 직렬화의 SHA-256이며 원본 식별자나 전역 캐시 키로 사용하지 않는다.

## 3. 불변 프로필과 활성 정책

### text_analysis_profiles

| 컬럼 | 타입·제약 | 의미 |
| --- | --- | --- |
| id | uuid PK | 프로필 ID |
| name | text UNIQUE NOT NULL | 운영 식별 이름 |
| model_name | text NOT NULL | 지정 모델 ID |
| model_revision | text NOT NULL | 고정 commit, main 금지 |
| tokenizer_revision | text NOT NULL | 고정 tokenizer commit |
| input_format_version | text NOT NULL | title/description 직렬화 |
| language_rule_version | text NOT NULL | 한국어·영어·혼합 입력 처리 |
| keyword_rule_version | text NOT NULL | 정규화·사전·부정 처리 |
| runtime_config | jsonb NOT NULL | 라이브러리 버전, 생성·분할 옵션 |
| fingerprint | text UNIQUE NOT NULL, 64자리 소문자 hex CHECK | 모든 실행 설정의 canonical hash |
| created_at | timestamp NOT NULL | 생성 시각 |

runtime_config는 JSON object CHECK를 둔다. fingerprint는 서비스에서 재계산 검증한다. 프로필 내용 UPDATE는 DB 트리거로 거부한다. 실제 commit·버전은 호환성 검증 후 채우며 빈 placeholder 프로필을 활성화하지 않는다.

### matching_policies / matching_runtime

matching_policies: `id uuid PK`, `analysis_profile_id uuid NOT NULL FK RESTRICT`, `rule_version text NOT NULL`, `config jsonb NOT NULL`, `fingerprint text UNIQUE NOT NULL`(64자리 hex CHECK), `created_at timestamp NOT NULL`. 불변 트리거와 config object CHECK를 둔다. 초기 config는 건물 OR 공통 키워드, KST 날짜 하한 규칙을 명시한다.

matching_runtime: `id integer PK CHECK(id=1)`(자동 증가 없음), `active_policy_id uuid NOT NULL FK RESTRICT`, `generation bigint NOT NULL CHECK(generation>0)`, `updated_at timestamp NOT NULL`. 정책 변경 시 generation을 DB 트리거가 증가시킨다. 검증된 프로필과 활성 정책은 런타임 구현 시 등록하며 이번 DB 마이그레이션에서는 빈 테이블로 둔다. 전체 원본의 재분석/재평가 작업 생성은 정책 전환 서비스의 책임이다. 다른 프로필 결과를 섞지 않는다.

초기 프로필 교체는 유지보수 모드에서 수행한다. 새 프로필을 비활성 상태로 backfill한 뒤 활성 정책 전환·재평가를 완료하고 쓰기를 재개한다. 무중단 이중 정책 제공은 후속 범위다.

## 4. 분석 결과 테이블

found_item_text_features와 lost_report_text_features는 아래 공통 구조를 가지며 FK 이름만 각각 item_id/report_id다.

| 컬럼 | 타입·제약 |
| --- | --- |
| id | uuid PK |
| item_id 또는 report_id | uuid NOT NULL FK 원본 ON DELETE CASCADE |
| profile_id | uuid NOT NULL FK text_analysis_profiles ON DELETE RESTRICT |
| text_version | bigint NOT NULL CHECK > 0 |
| source_hash | text NOT NULL, 64자리 소문자 hex CHECK |
| source_language | text NOT NULL CHECK IN ('KO','EN','MIXED') |
| status | text NOT NULL CHECK IN ('PENDING','PROCESSING','READY','FAILED','SUPERSEDED') |
| translated_text | text NULL; title/description 경계를 보존한 영어 입력 |
| keywords | text[] NULL; 정렬·중복 제거한 canonical 토큰 |
| attributes | jsonb NULL; 종류별 구조화 특징 |
| created_at, updated_at | timestamp NOT NULL |
| completed_at | timestamp NULL |
| last_error_code | text NULL; 제한된 오류 코드 |

UNIQUE(원본 FK, profile_id, text_version)를 둔다. READY는 translated_text·keywords·attributes·completed_at이 모두 NOT NULL이고 last_error_code가 NULL이다. attributes는 object, keywords는 1차원 또는 빈 배열이며 NULL 원소를 금지한다. READY가 아니면 결과 세 컬럼은 NULL이다. FAILED는 completed_at과 error code가 필수이며, SUPERSEDED는 completed_at 필수다. PENDING/PROCESSING은 completed_at이 NULL이다. READY 결과는 수정하지 않고 새 버전/프로필을 생성한다.

빈 keywords 배열은 정상이다. source_language 분류는 서비스가 수행하며 미지원 언어는 임의 영어 처리하지 않고 FAILED로 남긴다. 원문 전체는 저장하지 않는다. 원본과 버전이 맞을 때 읽어 처리한다. 이전 버전 원문을 보관하지 않으므로 입력이 바뀐 미완료 작업은 SUPERSEDED로 종료한다. 이전 READY 행도 최신 버전 조인에서 제외한다.

## 5. Outbox 분석 작업

기존 outbox_events의 unique(aggregate_id, aggregate_version, event_type)는 유지한다. 새 분석 이벤트는 원본 ID 대신 **분석 행 ID**를 aggregate_id로 사용하고 aggregate_version=1로 고정한다. 프로필·버전마다 분석 행 ID가 다르므로 같은 원본의 여러 프로필 작업이 충돌하지 않는다.

| event_type | aggregate_id | payload |
| --- | --- | --- |
| FOUND_ITEM_TEXT_ANALYSIS_REQUESTED | found_item_text_features.id | featureId, itemId, profileId, textVersion |
| LOST_REPORT_TEXT_ANALYSIS_REQUESTED | lost_report_text_features.id | featureId, reportId, profileId, textVersion |

추가 컬럼: `lease_token uuid NULL`, `failed_at timestamp NULL`, `cancelled_at timestamp NULL`. lease_until과 lease_token은 둘 다 NULL이거나 둘 다 NOT NULL이다. processed_at, failed_at, cancelled_at은 최대 하나만 채운다. 완료/실패/취소 시 lease를 비운다. 분석 FAILED와 outbox failed_at은 같은 트랜잭션에서 기록한다. 최대 시도 실패를 성공 processed_at으로 위장하지 않는다.

기존 pending 부분 인덱스를 `processed_at IS NULL AND failed_at IS NULL AND cancelled_at IS NULL` 조건으로 교체한다. 소비 쿼리는 event_type 허용 목록과 next_attempt_at, lease 만료를 함께 검사한다. 다른 알림·스토리지 이벤트 소비자도 이 종료 조건을 반영해야 한다.

획득은 짧은 트랜잭션의 SELECT FOR UPDATE SKIP LOCKED → attempts 증가·새 lease_token·lease_until 설정이다. 추론 중에는 DB 잠금을 유지하지 않는다. 갱신·완료·실패 쓰기는 ID, 현재 token, 종료되지 않음, 미만료 lease 조건을 모두 검사하고 1행 갱신을 확인한다. 갱신 0행이면 결과를 버린다. 긴 추론은 heartbeat로 lease를 연장한다.

수동 재시도는 같은 이벤트의 failed_at을 지우고 attempts를 초기화하며 분석 행을 PENDING으로 되돌린다. 현재 원본 버전과 일치하지 않으면 재시도하지 않고 최신 작업을 만든다.

## 6. 재평가 작업 테이블

후보 재평가는 단순 원본 버전별 outbox 하나만으로 처리하지 않는다. 같은 원본 버전에서도 반대편 분석 완료로 다시 평가해야 하기 때문이다.

`match_evaluation_jobs`:

| 컬럼 | 타입·제약 |
| --- | --- |
| id | uuid PK |
| item_id, report_id | nullable FK 각 원본 ON DELETE CASCADE |
| policy_id | uuid NOT NULL FK matching_policies RESTRICT |
| requested_generation | bigint NOT NULL DEFAULT 1 CHECK > 0 |
| completed_generation | bigint NOT NULL DEFAULT 0 CHECK >= 0 AND <= requested_generation |
| claimed_generation | bigint NULL |
| lease_token, lease_until | uuid NULL, timestamp NULL |
| attempts | integer NOT NULL DEFAULT 0 CHECK >= 0 |
| next_attempt_at | timestamp NOT NULL |
| failed_at, last_error_code | timestamp NULL, text NULL |
| created_at, updated_at | timestamp NOT NULL |

CHECK로 item_id와 report_id 중 정확히 하나만 필수로 한다. UNIQUE(item_id, policy_id)와 UNIQUE(report_id, policy_id)를 각각 둔다. claimed_generation/token/lease_until은 모두 NULL이거나 모두 NOT NULL이며, claimed_generation은 1 이상 requested_generation 이하다.

원본 변경·분석 완료마다 대상 작업을 UPSERT하고 requested_generation을 1 증가시킨다. 기존 lease는 빼앗지 않는다. 처리 중 추가 요청이 오면 성공 시 claimed_generation까지만 완료한다. completed < requested이면 다시 실행하여 요청 유실을 막는다. 실패 시에도 새 요청이 있으면 failed_at을 해제하고 즉시 재시도 대상으로 둔다. 한 페이지씩 처리하고 전체 페이지 완료 후에만 completed_generation을 갱신한다. 중간 중단은 처음부터 안전하게 재실행한다.

양쪽 분석 완료 시 각각 자기 원본의 작업을 요청한다. 나중에 READY가 된 쪽의 작업이 먼저 완료된 상대를 발견한다. 종료·삭제·조건 변경 시에는 기존 후보도 재평가 대상에 포함하여 새 적격 집합에서 빠진 후보를 비활성화한다. 건물 판정은 텍스트 미완료여도 수행하되 작업의 텍스트 판정은 미완료로 남기고 분석 완료 이벤트로 다시 요청한다.

## 7. match_candidates 확장

기존 report_id/item_id 유일 키, matched_at, first_notified_at, building_matched, keyword_matched를 유지한다. 의미 점수 컬럼으로 교체하지 않는다.

추가 컬럼:

- policy_id uuid NULL FK RESTRICT: 기존 행 이행을 위해 nullable, 신규 판정에는 필수.
- evaluated_item_version, evaluated_report_version bigint NULL CHECK > 0.
- item_feature_id, report_feature_id uuid NULL: 각 분석 테이블 FK, NO ACTION DEFERRABLE INITIALLY DEFERRED. 원본 삭제 시 후보·분석 CASCADE가 함께 완료될 수 있도록 커밋 시 검사한다.
- common_keywords text[] NOT NULL DEFAULT '{}'.
- legacy_evidence jsonb NULL: 기존 임베딩 정책의 의미 점수·판정 버전·활성 여부 이력. object CHECK를 두며 새 키워드 판정에 사용하지 않는다.

분석 FK가 다른 원본·프로필을 가리키지 않도록 분석 테이블의 UNIQUE(id, 원본 FK, profile_id)와 후보에 저장하는 analysis_profile_id를 이용한 복합 FK를 둔다. 후보의 (policy_id, analysis_profile_id)도 정책의 UNIQUE(id, analysis_profile_id)에 복합 참조한다. 기존 행은 이 필드를 모두 NULL로 둔다.

신규 정책 행은 양쪽 evaluated version이 필수다. keyword_matched=true이면 양쪽 feature ID 필수 및 cardinality(common_keywords)>0이다. keyword_matched=false이면 common_keywords는 빈 배열이다. active는 기존대로 building_matched OR keyword_matched를 요구한다. READY 여부·현재 text_version·공통 토큰의 실제 교집합은 저장 트랜잭션에서 검사한다. CHECK로 다른 행의 최신 상태를 검증한다고 가정하지 않는다.

원본 삭제 시 후보와 분석 행이 함께 제거되며 커밋 시 참조 무결성을 검사한다. 분석 이력만 정리할 때는 참조 후보가 남아 있으면 삭제할 수 없다. 신규 후보 갱신은 report/item 쌍의 같은 행을 사용하고 최초 시각·최초 알림을 덮어쓰지 않는다.

## 8. 트랜잭션과 최신성

### 분석 저장

원본·활성 정책·입력 버전 확인 → 원문 읽기 → 커밋 → 추론 → 원본 행 재잠금 → text_version과 lease token 재검증 → READY와 재평가 요청과 outbox 완료를 원자 커밋한다. 현재 일반 version만 바뀌고 text_version이 같으면 분석은 재사용할 수 있다.

### 후보 판정

초기에는 카테고리별 PostgreSQL transaction advisory lock을 사용한다. 이 잠금은 후보 집합 변경과 수거 검증의 직렬화 계약이다. 원본 등록·수정·종료·숨김·삭제, 건물 연결 변경, 후보 저장, 수거의 모든 경로가 동일 계약에 참여해야 한다. 카테고리 이동은 이전/이후 카테고리 잠금을 정렬 순서로 모두 얻는다. 관련 트랜잭션은 READ COMMITTED를 사용한다.

잠금 순서는 카테고리 advisory lock → 물품 UUID 순 → 신고 UUID 순 → 분석/후보/작업 행 순이다. 분석 완료가 재평가 작업을 갱신하는 경로도 같은 순서를 따른다. 작업 획득 트랜잭션은 lease 커밋 후 원본 잠금을 얻으므로 순서를 뒤집지 않는다. 모델 추론 중 advisory lock을 잡지 않는다.

판정 계산을 잠금 밖에서 수행했다면 저장 시 양쪽 version·profile·text_version·활성 policy를 다시 검사한다. 불일치 시 후보를 저장하지 않고 재요청한다. 후보 갱신과 신규 알림 이벤트는 같은 트랜잭션이다.

### 수거 시 최신 집합 보장

수거 트랜잭션은 관련 카테고리 잠금을 얻은 뒤 현재 적격 원본 집합을 다시 조회한다. 필요한 최신 분석이 READY가 아니면 변경을 롤백하고 MATCHING_PENDING을 반환한다. 준비됐으면 저장 후보만 신뢰하지 않고 최신 조건과 키워드로 해당 수거 판정 범위를 직접 재평가한 뒤 기존 FR-22 처리와 신고 종료를 수행한다. 번역은 이 트랜잭션 안에서 하지 않는다.

이 잠금이 유지되는 동안 신규 등록·수정이 같은 집합에 끼어들지 못한다. 비동기 작업 READY 표시는 전체 카테고리의 무변경 보장이 아니다. 카테고리별 직렬화 비용은 초기 정확성 우선 선택이며 부하 측정 후 범위 축소를 검토한다. 실제 FR-22 대상 범위는 기존 수거 명세에 맞춰 서비스 구현에서 테스트한다.

### 조회와 알림

현재 policy와 양쪽 원본 version에 맞는 후보만 최신 판정으로 노출한다. 일괄 재평가 중에는 matchingStatus=PROCESSING과 완전하지 않은 결과임을 응답한다. 분석 실패나 미완료는 키워드 불일치로 확정하지 않는다. 건물 근거는 현재 원본에서 다시 확인할 수 있다. 종료 신고는 기존 이력 정책으로 별도 조회하고 신규 알림을 만들지 않는다.

## 9. 인덱스와 보존

- 각 분석 테이블 UNIQUE(원본 FK, profile_id, text_version): 현재 결과 조인과 중복 방지.
- 각 분석 테이블 (profile_id, status, 원본 FK): backfill·정합성 복구.
- 초기 후보 비교는 카테고리·날짜로 좁힌 뒤 정확 키워드 교집합을 계산한다. 키워드 역색인/GIN은 실행계획 측정 후 추가한다.
- found_items의 (category_id, found_at, id) WHERE deleted_at IS NULL을 추가 검토한다. 기존 인덱스는 건물이 found_at보다 앞에 있어 건물 미지정 조회에 그대로 최적이라고 가정하지 않는다.
- 재평가 작업 (next_attempt_at, id) WHERE completed_generation < requested_generation AND failed_at IS NULL.
- outbox의 수정된 pending 인덱스와 기존 활성 후보 목록 인덱스 유지.

원본 영구 삭제 시 분석도 제거하고 분석 outbox는 같은 트랜잭션에서 cancelled_at으로 종료한다. 논리 삭제 시에도 번역문·키워드 결과를 지우고 후보를 기존 규칙대로 제거한다. outbox payload에는 ID와 버전만 있으므로 대상 소멸 시 재실행은 취소 처리한다. lease 소유자는 삭제 후 결과를 복원할 수 없다.

분석 이전 버전은 참조 후보가 없을 때 7일 후 정리하는 초기 운영안을 사용한다. 이는 원문 이력 보존 기능이 아니다. 최신 결과는 원본의 보존 기간을 따르고, 종료 신고 private details는 기존처럼 즉시 삭제한다. 완료 outbox는 기존 단기 보존 정책을 따른다. 실패 작업은 오류 코드와 식별자만 유지한다.

## 10. 마이그레이션 순서와 검증

1. 기존 개발 DB가 가리키던 `20261106_0005` 마이그레이션을 Git 이력 `79af37a`에서 원본 그대로 복원했다. 새 revision은 `20261107_0006`이며 그 위에 연결한다.
2. 기존 description_version을 text_version으로 이름 변경해 카운터를 보존하고 제목 변경도 증가시키는 새 트리거를 적용한다. 프로필·정책·런타임·분석·재평가 테이블과 outbox 확장을 추가한다.
3. 기존 의미 점수·버전은 legacy_evidence로 옮긴 뒤 전용 컬럼을 제거한다. 후보 ID·최초 시각·최초 알림은 유지하고 건물 근거가 없는 과거 후보는 재평가 전까지 비활성화한다. 기존 lease는 token과 만료 시각을 모두 비워 재획득하게 한다. 이행 중 기존 소비자는 중지해야 한다.
4. 호환성 검증을 마친 프로필을 등록하고 기존 원본의 현재 분석 작업을 배치 생성한다.
5. 새 소비자를 실행해 분석하고 새 정책으로 후보를 재평가한다. 구 키워드 판정을 새 정책 근거로 복사하지 않는다.
6. 새 정책 활성화 후 policy_id NULL인 후보는 현재 목록에서 제외하고 신규 판정에 필수인 서비스 검증을 적용한다.
7. API·DB의 동기 매칭 설명을 새 계약으로 갱신한다.

마이그레이션 도입 시 실행 중인 backend 컨테이너 /app에서 기존 db의 별도 kaifind_test_* DB로 upgrade/downgrade/upgrade, alembic check, 제약·경합 테스트를 수행한다. 개발 DB나 기존 볼륨을 삭제하지 않는다.

DB 테스트는 텍스트 버전·프로필 불변성·READY 정합성·FK 근거·outbox 제약·SKIP LOCKED와 조건부 token 갱신·generation 추가 요청·삭제 취소·기존 데이터 이행을 검증한다. 실제 소비자의 token 조건 적용, 양쪽 동시 분석 완료, 최신 후보 재평가·알림 중복 방지, 수거와 등록/카테고리 이동 경합은 서비스 구현 후 검증해야 한다.

다운그레이드는 신규 분석·정책·작업 테이블과 결과를 제거한다. 기존 의미 메타데이터는 legacy_evidence에서 복원하지만 새 키워드 후보를 의미 후보로 재해석하지 않으며 활성 상태를 자동 복구하지 않는다. 왕복 검증은 별도 테스트 DB에서만 수행했다.
