# 5단계: matching API·재평가 설계와 구현

작성일·구현일: 2026-11-08 (KST). MATCH-01·상태 조회·generation 소비자를 구현했다.
4단계 원본 API 연결과 6단계 알림·수거 통합 완료를 뜻하지 않는다.

## 범위와 명세 대조

[API 목록](../api/README.md), [공통 규칙](../api/00-common.md),
[신고·매칭](../api/03-lost-reports-matching.md),
[기존 구현 계획](translation-keyword-implementation-plan.md),
[3단계 호출 계약](text-analysis-worker.md)을 기준으로 한다.
기존 경로·DTO·인증·페이지·정렬·매칭 세 조건은 유지한다. 새 회원용 실행·재시도 API는 추가하지 않는다.

4단계는 팀원이 원본 API를 구현한다. 5단계는 기존 DB 원본과 3단계 요청 함수를 사용해
독립적으로 개발·검증할 수 있다. 실제 HTTP 등록 → 분석 → 후보 조회의 통합 검증은 4단계 연결 후 수행한다.
알림 생성·이메일·수거 판정·관리자 숨김 쓰기 경로 연결은 6단계다.

명세의 ‘현재 후보 연결 제거’는 기존 DB의 active=false로 구현한다. 행을 삭제하면 최초 발견 시각과
알림 중복 억제 이력을 잃으므로 같은 쌍의 행은 유지한다. 물품·신고 영구 삭제와 물품 논리 삭제는
기존 cascade·트리거를 따른다. 아래 비교 범위·건물 우선 판정·만료 조회 의미는 구현을 위한 세부 제안이다.

## 공개 API

`GET /api/v1/lost-reports/{reportId}/matches?page=0&size=20`

| 항목 | 계약 |
| --- | --- |
| 인증 | KAIFIND_SESSION, MEMBER 또는 ADMIN |
| 권한 | 신고자 본인 또는 관리자. 다른 회원·없는 신고는 동일한 404 LOST_REPORT_NOT_FOUND |
| 입력 | UUID reportId, page>=0, 1<=size<=100. 미정의 query 거부 |
| 본문·CSRF | 없음 |
| 성공 | 200 MatchCandidatePage. 처리 중·분석 실패도 진행 상태를 포함한 200 |
| 헤더 | Cache-Control: no-store, Content-Language: ko 또는 en |
| 오류 | 기존 공통 400·401·500. 처리 중이라는 이유로 409 MATCHING_PENDING을 반환하지 않음 |
| 정렬 | matchedAt DESC, candidateId DESC |

응답은 schema/matching.py를 그대로 사용한다. 후보에는 candidateId, reportId, itemId,
matchedAt, matchedBy와 공개 item 요약만 포함한다. matchedBy는 BUILDING, KEYWORD 순서로 고정한다.
점수·번역·공통 키워드·사진·보관 위치·연락처·privateIdentifyingDetails는 노출하지 않는다.

부분 결과의 예:

```json
{
  "items": [],
  "page": 0,
  "size": 20,
  "totalElements": 0,
  "totalPages": 0,
  "analysisStatus": "READY",
  "matchingStatus": "PROCESSING",
  "isComplete": false
}
```

빈 items만으로 ‘일치 없음’을 확정하지 않는다. isComplete=true일 때만 현재 범위의 계산 완료다.
범위를 벗어난 페이지는 빈 items와 실제 전체 개수를 반환한다. 페이지 간에는 새 후보로 인한 이동이 가능하다.
조회는 모델 실행·작업 생성·재평가·신고 상태 변경을 하지 않는다.

## 비교 범위와 후보 판정

OPEN이며 expiresAt>now인 신고에 대해, 논리 삭제되지 않은 동일 카테고리 물품 중
foundAt의 KST 날짜가 lostDateFrom 이상인 전체를 비교 범위로 삼는다.
lostDateTo 상한, POSTED 한정, 민감 여부 조건을 추가하지 않는다.
hidden 물품도 내부 계산 범위에 포함하고 응답에서 권한별로 제거한다.
회원에게 숨김·삭제 물품은 제외한다. 관리자는 숨김 물품을 조회할 수 있고 삭제 물품은 제외한다.
집계 개수와 목록에 동일 필터를 적용한다.

각 쌍의 조건은 `카테고리 동일 AND 날짜 하한 충족 AND (건물 일치 OR 공통 canonical 키워드 존재)`다.

- 건물 일치는 분석 미완료·실패에도 확정 가능한 BUILDING 후보로 저장할 수 있다.
- KEYWORD는 양쪽 현재 text_version과 활성 프로필의 분석이 READY일 때만 인정한다.
  기존 common_keywords 비교 규칙을 재사용하며 서로 다른 프로필은 비교하지 않는다.
- 양쪽 분석이 준비되면 건물 후보도 재평가해 KEYWORD 근거를 보완한다.
- 양쪽 분석이 미완료이고 건물도 다르면 후보를 추측하지 않는다.
- 기존 후보가 조건을 잃으면 비활성화한다. 변경 직후 재평가 전의 오래된 후보도 조회에서 제외한다.

후보 UPSERT는 (report_id, item_id) 유일 키를 사용한다. 최초 insert의 id·matched_at을 유지하고,
재등장 시 active=true로 복원하며 근거·정책·양쪽 version·분석 참조·last_evaluated_at만 갱신한다.
first_notified_at은 5단계에서 변경하지 않는다. 6단계는 이 이력과 고유 이벤트 키로 중복을 억제해야 한다.

## 최신성·진행 상태

OPEN 신고의 후보는 active=true, 현재 정책·프로필 일치, evaluated_item_version과
evaluated_report_version의 현재 원본 version 일치가 필요하다. KEYWORD 근거는 현재 양쪽
feature의 READY·text_version까지 검사한다. 과거 정책·legacy 후보는 재평가 전 노출하지 않는다.
generation 미완료라는 이유만으로 별개의 최신 후보까지 모두 숨기지는 않는다.

analysisStatus는 기존 analysis_status(db, owner=report)를 사용한다.
matchingStatus는 신고 자신의 분석·재평가 및 비교 범위의 물품 분석·재평가를 집계한다.
현재 정책·현재 입력에 속한 상태만 사용하고 과거 실패를 끌어오지 않는다.

| 상태 | 판정 |
| --- | --- |
| FAILED | 현재 범위에 최종 실패한 분석 또는 미완료 재평가 작업 존재 |
| PROCESSING | 실패가 없고 분석 실행 중 또는 유효한 재평가 lease 존재 |
| PENDING | 위 상태가 없고 필요한 분석·작업 누락 또는 requested_generation>completed_generation |
| READY | 필요한 분석 모두 READY, 필요한 작업 모두 최신 generation 완료 |

우선순위는 FAILED > PROCESSING > PENDING > READY다. 만료 lease는 실행 중으로 보지 않는다.
재시도 대기 중인 작업은 PENDING이고, 최종 실패만 FAILED다. 비교 물품이 없어도 신고 자신의
분석·재평가가 끝나야 READY다. 건물 후보가 있어도 분석 실패를 숨기지 않는다.
isComplete는 matchingStatus=READY와 정확히 일치한다.

페이지·전체 개수·상태는 하나의 SQL 문과 CTE로 같은 statement snapshot에서 읽는다.
ProtectedRoute 인증 쿼리 이후 트랜잭션 격리를 변경하지 않는다. READ COMMITTED에서
COUNT·목록·상태를 별도 실행해 서로 다른 시점의 응답을 조합하지 않는다.
신고 존재·권한 검사도 최종 조회 조건에 포함한다. 기준 시각은 request.state.now를 사용한다.

## 종료·만료 신고

RESOLVED·CLOSED 신고는 보존된 active 후보 목록을 반환한다. 종료 때문에 증가한 신고 version이나
정책 변경으로 과거 후보를 숨기지 않고, 숨김·삭제·권한 필터는 적용한다.
matchingStatus=READY, isComplete=true는 이력 목록 완료를 뜻한다.
analysisStatus는 마지막 보존 상태다. 신규 분석·재평가·알림은 만들지 않는다.

상태가 아직 OPEN이어도 expiresAt<=now라면 조회는 동일하게 이력으로 취급한다.
이 GET에서 CLOSED 변경이나 private 삭제를 수행하지 않는다. 실제 종료·개인정보 정리는
4단계 만료 처리 책임이며 지연 정리를 허용한다는 뜻은 아니다. 워커도 만료 신고에 신규 후보를 생성하지 않는다.

## generation 재평가 워커

기존 match_evaluation_jobs와 backend 프로세스를 사용한다. 별도 컨테이너·메모리 큐는 만들지 않는다.
item 작업은 해당 물품과 적격 신고 및 기존 연결 신고를, report 작업은 해당 신고와 비교 물품 및
기존 연결 물품을 방문한다. 이전 카테고리의 기존 연결도 정리 대상에 넣는다.

1. 짧은 SKIP LOCKED 트랜잭션으로 미완료 작업을 확보한다. claimed_generation과 새 lease token을 기록한다.
2. 처리 대상 카테고리 스냅샷을 읽고 모든 관련 카테고리 잠금을 실제 key 순으로 한 번에 획득한다.
   원본 행은 물품 UUID 순 → 신고 UUID 순, 이후 분석·후보·작업 순으로 잠근다.
3. 카테고리 스냅샷·정책·원본·만료·lease를 재검사한다. 이동했으면 전체 트랜잭션을 재시도한다.
   카테고리를 뒤늦게 추가 잠금하지 않는다.
4. 추론 없이 저장된 분석으로 후보를 계산·UPSERT·비활성화한다.
5. 같은 트랜잭션에서 token·유효기간을 다시 확인하고 completed_generation을 확보한 generation까지만 전진시킨다.
   새 요청이 들어왔으면 requested_generation을 덮어쓰지 않고 다음 실행 대상으로 남긴다.

작업 확보 트랜잭션의 행 잠금을 본 처리까지 유지하지 않는다. lease만으로 후보 갱신을 허용하지 않고
최종 저장 시 fencing한다. 만료된 이전 워커의 성공·실패는 모두 무효다.
분석 대기는 최종 실패로 처리하거나 빠르게 반복 재시도하지 않는다. 현재 확정 가능한 건물 후보를 저장하고
백오프로 재확인한다. 분석 완료 시 3단계가 owner 재평가 generation을 증가시키므로 반대편 쌍도 다시 방문한다.
최종 분석 실패에서는 건물 결과를 유지하되 matchingStatus=FAILED를 반환한다.

초기 구현은 작업 하나의 비교·갱신을 한 트랜잭션으로 수행한다. 중간 batch마다 완료 표시하지 않는다.
대규모 카테고리의 긴 잠금은 부하 검증 대상이며, 이후 분할하려면 진행 cursor·범위 완료 증거를 먼저 설계한다.
lease·heartbeat·백오프·최대 시도는 기존 분석 워커 기본값을 출발점으로 사용하되,
분석 대기를 실제 처리 오류 attempts와 구분한다. 장애 복구는 누락 작업 보완·만료 lease 회수·감사된 운영 재시도로 설계한다.
분석 대기는 5초 후 재확인하고 오류 attempts에 포함하지 않는다. 실제 처리 오류는 최대 5회,
최대 300초의 지수 백오프와 jitter로 재시도한다. 회원용 실행·재시도 API는 없다.

## 파일·팀 연결 계약

| 영역 | 구현 |
| --- | --- |
| router/matching.py | ProtectedRoute, MatchingParams, MatchCandidatePage, request.state 컨텍스트 연결 |
| service/matching.py | 후보 판정·페이지 조회·matching_progress(db, report, now) 제공 |
| service/matching_worker.py | generation 확보·lease·후보 저장·재시도 |
| 앱 lifespan | 기존 분석 소비자와 별도로 matching 소비자 시작·종료 |
| tests/test_matching_*.py | 순수 판정·PostgreSQL 경합·HTTP 권한/진행 상태 검증 |

Pydantic 모델은 기존 schema/matching.py·matching_params.py를 재사용한다.
4단계 서비스는 matching_progress를 응답 DTO에 연결하고 기존 3단계 요청 함수를 호출한다.
matching_progress는 읽기 전용이며 commit·모델 실행을 하지 않는다.
4단계 담당 서비스·라우터·schema를 5단계가 동시에 수정하지 않는다.
기존 active·version 증거·generation·lease를 사용한다. revision 20261108_0008은
감사 action MATCH_EVALUATION_RETRIED만 추가하고 기존 데이터를 수정하지 않는다.

## 구현 순서와 완료 기준

1. 순수 판정과 최신성 조건·범위 집계 쿼리를 구현한다.
2. generation 워커와 후보 유일성·비활성/재등장·lease fencing을 구현한다.
3. MATCH-01을 연결하고 OpenAPI·오류·헤더·개수/페이지 일관성을 검증한다.
4. 4단계 담당자와 진행 상태 조회를 연결하고 원본 HTTP 흐름을 통합 검증한다.

필수 검증은 다음과 같다.

- 타 회원 404·관리자 조회, 비공개 필드/사진/연락처 부재, 알 수 없는 query·페이지 범위 거부.
- 건물만 일치·키워드만 일치·둘 다 일치·불일치, KST 날짜 경계와 lostDateTo 이후 발견 허용.
- 분석 대기/실패 중 건물 후보, 분석 완료 후 근거 보완, 부분 결과·READY 빈 결과 구분.
- 신규 반대편 물품·신고가 생기면 기존 READY를 즉시 미완료로 집계, 오래된 version·정책 결과 차단.
- 중복·양쪽 동시 처리·재등장 시 같은 candidateId/matchedAt 유지, 이전 카테고리 연결 비활성화.
- 처리 중 generation 증가·카테고리 이동·lease 만료·늦은 완료·롤백 후 재확보.
- 종료·만료·삭제와 처리 경합, 종료 이력 보존, GET 전후 분석/작업/후보/알림 행 불변.
- 회원 숨김 필터와 전체 개수 일치, 한 응답 안에서 상태·목록·개수 snapshot 일치.

실행은 기존 backend 컨테이너 /app에서만 하며 기존 db의 kaifind_test_* DB를 사용한다.
부하·실제 알림·수거 통합과 4단계 HTTP 등록/수정 전체 흐름은 별도 검증 대상이다.

## 실행과 복구

기존 backend 컨테이너 /app에서 실행한다. 기존 활성 분석 정책·프로필을 그대로 사용한다.

```sh
docker compose exec -T -w /app backend python -m alembic upgrade head
docker compose exec -T -w /app backend python -m scripts.manage_matching repair
docker compose exec -T -w /app backend python -m scripts.manage_matching retry <job-uuid>
```

TEXT_ANALYSIS_ENABLED=true이면 lifespan에서 분석 소비자와 matching 소비자를 함께 시작하고 종료한다.
false이면 둘 다 시작하지 않는다. matching 소비자는 추론 런타임을 직접 사용하지 않는다.
repair는 원본 UUID keyset 100개 단위로 활성 정책의 누락된 작업만 보완한다. 기존 최종 실패를 초기화하지 않는다.
신고 종료·물품 삭제·기한 만료 대상은 새 작업을 만들지 않는다. 분석 행/outbox 누락은 기존
manage_text_analysis repair로 보완해야 한다. 주기적인 자동 repair는 추가하지 않았다.

retry는 활성 정책의 적격 원본에 대한 실패 작업만 받는다. 요청 generation을 증가시키고 실패를 해제하며
SYSTEM/MATCH_EVALUATION_RETRIED를 같은 트랜잭션으로 기록한다. metadata.eventId는 작업 UUID다.
감사 이벤트가 남아 있으면 0008 downgrade는 이력을 보존하기 위해 거절한다.
이미 끝난 generation이나 이전 정책의 실패를 임의로 다시 활성화하지 않는다.

## 검증 결과

2026-11-08: 실제 모델 활성 전체 457개 테스트가 skip 없이 통과했다. 추가로 실제 한국어 분석에서
KEYWORD 후보까지의 통합 1개, 이전 generation의 최종 실패가 새로운 요청을 막지 않는 경합 1개를 검증했다.
총 고유 459개를 검증했으며 pip check·alembic check·git diff --check도 통과했다.
기존 pytest-asyncio fixture loop scope·SWIG deprecation 경고는 남아 있다.
개발 DB 0008 적용 전후 사용자·물품·신고·사진 행 수 보존, 루트 200과 실행 중 MATCH-01 OpenAPI를 확인했다.
4단계 HTTP 등록/수정 전체 흐름·6단계 연결·운영 부하·이미지 재빌드는 검증하지 않았다.
