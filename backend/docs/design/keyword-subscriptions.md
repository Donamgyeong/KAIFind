# 키워드 구독 구현 설계

2026-11-09. KEYWORD-01~03과 신규 습득물 키워드 알림을 구현했다. 실제 습득물 등록 HTTP API는 아직 501이며, DB INSERT 트리거로 등록 이벤트를 연결한다.

참조: [API 목록](../api/README.md), [공개 계약](../api/04-profile-notifications.md), [런타임](translation-runtime.md), [이메일](notification-delivery.md).

## 전체 단어 판정

기존 번역·spaCy 분석 결과 중 `lemma:`, `term:`, `identifier:`, `number:`만 정렬·중복 제거하여 비교한다. 구독 집합 S, 물품 집합 I에 대해 `bool(S) and S <= I`이면 일치한다. 제목과 설명은 합치며 순서·단어 간 거리·반복 횟수는 검사하지 않는다.

| 구독 | 물품 | 결과 |
| --- | --- | --- |
| 검은, 지갑 | 검은, 가방 | 불일치 |
| 검은, 지갑 | 검은, 동전, 지갑 | 일치 |
| 검은, 지갑 | 지갑 | 불일치 |
| 빈 집합 | 임의의 물품 | 불일치 |

명사구 `phrase:`와 동의어 `wn:`를 필수 조건에서 제외한다. 따라서 단어 사이에 다른 단어가 있어도 일치하며, 동의어만 같은 서로 다른 표제어는 이번 구독에서는 일치하지 않는다. 원문 어절 전체가 아니라 번역·불용어 제거·표제어 추출 후의 긍정 특징 기준이다. 부정 처리는 기존 추출기를 따르고 별도 부정 조건은 지원하지 않는다. `검은 가방 옆의 지갑`도 일치할 수 있다. 수식 관계·번역 누락·다의어 품질을 보장하지 않는다.

분실 신고 후보 매칭의 카테고리·날짜·건물 OR 키워드 규칙과 동의어 지원은 변경하지 않는다.

## 구독 API와 인증

기존 경로·응답 모델을 유지한다. GET은 본인 구독을 createdAt DESC·subscriptionId DESC로 반환하며 page=0, size=20, 최대100이다. POST는 trim 후 1~50자 문자열만 받고 미정의 필드·타입 오류·null을 거부한다. 표시값은 trim한 원문, 중복 키는 NFKC 후 lower다. UNIQUE(user_id,normalized_keyword)로 동시 중복도 409 KEYWORD_ALREADY_SUBSCRIBED를 반환한다. 의미상 같더라도 문자열 중복 키가 다르면 별도 구독이다.

POST는 KeywordCreateRoute를 통해 두 번 인증한다.

1. 짧은 보호 트랜잭션에서 세션·CSRF·Origin·JSON·모델·중복·활성 프로필을 검증한다.
2. 세션과 DB 잠금을 모두 닫고 `AnalysisInput(description=keyword)`를 상주 런타임으로 분석한다.
3. 같은 세션 ID와 현재 세션 유효성·CSRF·권한·활성 프로필을 다시 검사한다. 런타임 설정 행·사용자 행을 잠근 뒤 구독과 READY 특징을 함께 저장한다.
4. 커밋 후 201, Location: /api/v1/me/keyword-subscriptions/{subscriptionId}를 반환한다.

추출 단어가 없으면 400 VALIDATION_ERROR와 keyword 필드 NO_MATCHABLE_TERMS다. 분석 비활성·busy·timeout·프로필 불일치는 503 KEYWORD_ANALYSIS_UNAVAILABLE와 Retry-After: 5이며 구독을 저장하지 않는다. 응답에 분석 상태 필드를 추가하지 않는다. 응답 유실 후 재요청은 409가 될 수 있으므로 목록에서 확인한다. 원문·모델 예외는 로그나 오류 응답에 넣지 않는다.

DELETE는 사용자 행 다음 구독 행을 잠그고 본인 구독만 삭제한다. 타인·없는 ID는 404, 성공은 본문 없는 204다. 특징·알림 근거는 CASCADE로 제거한다. 인앱 알림은 유지하며, 남은 근거가 없으면 기존 이메일 발송 직전 검사에서 개별·요약 메일을 제외한다. 이미 외부 호출이 시작된 메일은 회수하지 못한다. 재등록은 새 ID이고 과거 알림 근거를 복원하지 않는다.

## DB와 등록 시점

revision `20261109_0010`은 아래 구조를 추가한다. 기존 물품의 등록 이벤트는 backfill하지 않는다. 기존 구독은 유지하며 신규 이벤트를 평가할 때 필요한 프로필 특징을 지연 생성한다.

| 구조 | 역할 |
| --- | --- |
| keyword_registration_order 시퀀스 | 구독·물품의 전역 등록 순서 |
| keyword_subscriptions.registration_order | 구독이 유효해진 순서 |
| keyword_subscription_features | 구독·분석 프로필·규칙별 READY 또는 FAILED 특징. terms, source_hash, completed_at, last_error_code |
| keyword_registration_events | 물품별 UNIQUE 등록 스냅샷 겸 영속 작업 큐. 고정 event ID, 프로필·규칙, terms, 수신자 커서, lease·재시도·오류·완료 시각 |

구독 INSERT의 BEFORE 트리거와 습득물 INSERT의 AFTER 트리거가 같은 advisory transaction lock(73011810)을 잡고 순번·DB 시각을 부여한다. 구독 순번 < 물품 등록 순번인 구독만 대상이다. 시각 동률·시계 이동에도 순번으로 소급을 방지한다. 등록 트랜잭션의 나머지 단계에서 이 잠금 보유 후 다른 사용자·카테고리 잠금을 새로 얻지 않는 순서를 유지해야 한다.

물품 INSERT와 같은 트랜잭션에서 공개 제목·설명을 동결한다. 별도 outbox는 만들지 않고 등록 이벤트 테이블 자체를 큐로 사용한다. 사진·비공개 정보·보관 위치는 저장하지 않는다. 분석 성공 후 원문 스냅샷을 제거한다. 등록 후 수정은 등록 이벤트를 바꾸거나 새로 만들지 않는다. 기존 FoundItemTextFeature는 현재 버전 검사 때문에 옛 버전을 폐기할 수 있어 등록 분석은 같은 런타임을 사용하는 독립 작업으로 처리한다. 현재 특징 재사용 최적화는 구현하지 않았다.

활성 정책이 없는 환경에서도 INSERT는 스냅샷을 남기며 profile_id는 null이다. 분석 워커가 처음 처리할 때 현재 활성 프로필에 고정한다. 이미 프로필이 있으면 등록 당시 값을 사용한다. 물품 숨김·삭제·POSTED 종료는 트리거로 이벤트를 CANCELLED로 만들고 원문·lease를 제거한다. 상태 복원으로 다시 열지 않는다. 영구 삭제는 FK CASCADE로 제거한다.

## 워커와 원자성

분석 활성 시 lifespan이 KeywordWorker를 기존 backend 프로세스에서 실행한다. 이벤트 상태는 PENDING → READY → DONE 또는 CANCELLED/FAILED다. 처리 대기는 next_attempt_at이며 별도의 WAITING 상태 행은 만들지 않는다.

1. SKIP LOCKED로 이벤트를 claim한다. lease는120초, heartbeat는40초다.
2. 트랜잭션 밖에서 등록 스냅샷을 분석하고 source_hash·프로필 fingerprint·규칙을 검사한다. 성공 시 terms 저장과 스냅샷 제거를 함께 커밋한다.
3. 수신자 UUID 오름차순으로 한 회원의 모든 구독을 평가한다. 같은 프로필 특징이 없으면 구독을 잠그지 않은 상태에서 분석하고 사용자→구독 잠금으로 생존 여부를 재확인한 뒤 저장한다.
4. 알림 트랜잭션은 물품→사용자→구독(ID 순)→이벤트 잠금 순서다. 삭제도 사용자→구독 순서다. lease token·만료·물품 상태·구독 생존·등록 순번을 재검사한다.
5. 일치 subscription_ids 전체를 모아 create_notification에 한 번 전달한다. 이벤트 ID·회원·종류 UNIQUE로 중복을 막는다. 인앱·모든 근거·이메일 큐·수신자 커서는 같은 트랜잭션이다. 회원 내부는 나누지 않는다.
6. 커밋 직전 lease 만료도 확인해 늦은 결과를 롤백한다. 전체 수신자가 끝나면 DONE으로 고정한다.

프로세스 종료 후 만료 lease는 재claim한다. busy·모델 준비 대기·특징 준비 대기는5초 후 재시도하며 실제 실패 횟수로 세지 않는다. 실제 실패는60초부터 최대1800초 backoff,10회 후 FAILED로 남긴다. FAILED 특징은 조용히 불일치 처리하지 않는다. 운영 retry는 해당 프로필의 FAILED 구독 특징도 제거하여 재분석 가능하게 한다. 원문을 잃은 작업은 retry를 거부한다.

이메일 off여도 인앱은 생성한다. 기존 keywordEmail·일일 한도·digest·발송 직전 구독 검사·mock 제공자를 재사용한다. 실제 외부 제공자는 연결하지 않는다.

## 프로필 변경과 보존

등록 이벤트는 프로필과 `all-atomic-terms-v1` 규칙을 고정한다. matching_runtime의 활성 정책을 변경할 때 다른 프로필의 PENDING/READY/FAILED 등록 이벤트가 남아 있으면 DB 트리거가 거부한다. 미완료 이벤트를 먼저 소진하거나 명시적으로 취소한 뒤 프로필을 전환한다. 완료된 과거 이벤트를 다시 평가하지 않는다. 새 프로필에서는 기존 구독 특징을 필요할 때 재분석한다.

cleanup 명령은30일이 지난 미분석 스냅샷을 CANCELLED(KEYWORD_SNAPSHOT_EXPIRED)로 전환하고 원문을 지운다. 완료·취소7일 후 terms·수신자 커서를 지우되 중복 방지를 위한 이벤트 ID·item_id·완료 표식은 물품 생존 기간 유지한다. 기존 알림 워커가 매시간 cleanup을 실행하며 분석 비활성 기간에도 동작한다. 필요하면 운영 명령으로 즉시 실행할 수 있다. 물품 삭제 시 원문 제거는 트리거로 즉시 적용한다.

마이그레이션 downgrade는 등록 이벤트 또는 분석 특징 이력이 있으면 거부한다. 운영 이력을 지우고 강제 downgrade하지 않는다.

```sh
docker compose exec -T -w /app backend python -m alembic upgrade head
docker compose exec -T -w /app backend python -m scripts.manage_keyword_subscriptions failures
docker compose exec -T -w /app backend python -m scripts.manage_keyword_subscriptions retry <event-uuid>
docker compose exec -T -w /app backend python -m scripts.manage_keyword_subscriptions cleanup
```

## 검증과 한계

테스트는 기존 backend /app과 별도 kaifind_test_* DB에서 수행한다. 집합 판정·API 입력/인증/CSRF/Origin·중복/페이지/계정 격리·추론 중 세션 만료/잠금 해제·등록 롤백/수정·복수 근거/삭제/이메일 off·재실행/동시 워커/lease 만료 롤백·실패 복구/보존 정리·마이그레이션 왕복과 이력 보존을 검사한다. 실제 한국어·영어 예시의 번역부터 전체 단어 판정까지 별도 모델 테스트로 확인한다.

대규모 구독 부하·장시간 장애·외부 메일 제공자는 미검증이다. 실제 습득물 등록 HTTP API는 별도 구현 영역이며 DB INSERT→이벤트→알림 경로를 검증한다. 추가 라이브러리는 없다.

2026-11-09 검증 결과: 전체 회귀641개 통과·실제 모델 관련5개 skip.
최종 프로필 연결 잠금 보완 후 구독 기능·실제 모델31개가 모두 통과했다.
실제 한국어·영어 예시 모델 검증은 별도 실행하여 skip 없이 확인했다.
개발 DB에0010을 적용했고 기존37개 테이블의 행 수를 보존했다.
alembic check는 추가 변경 없음, 실행 중 루트·OpenAPI는200, git diff --check는 통과했다.
분석 프로필 fingerprint를 유지하기 위해 구독 판정은 library/keyword_subscription_matching.py에 분리했다.
