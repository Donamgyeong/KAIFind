# 번역·키워드 매칭 구현 계획과 API 팀 인계

작성일: 2026-11-08 (KST). DB revision: `20261107_0006`.

## 범위와 담당 경계

사용자 지시에 따라 4단계 원본 API 구현은 다른 팀원이 담당한다. 이 작업의 담당은 1단계 공통 계약·기반과 후속 번역·작업·매칭 기능이다. 4단계 파일을 동시에 수정하지 않는다.

| 단계 | 범위 | 담당/상태 |
| --- | --- | --- |
| 1 | API 계약, 상태 DTO, 본문 없는 쓰기, 카테고리 잠금 함수 | 구현·검증 완료 |
| 2 | 실제 모델 로딩·번역·키워드 추출, 고정 프로필 검증 | 후속 |
| 3 | 분석 요청 함수, outbox 소비, lease·재시도·복구 | 후속 |
| 4 | 습득물·분실 신고 등록/수정/조회/종료 등 원본 API | 다른 팀원 |
| 5 | generation 기반 재평가·후보 조회 MATCH-01 | 후속 |
| 6 | 최초 알림, 이메일, 수거 최신성·관리자 숨김·정리 | 후속 |

4단계 소유 영역: `service/found_items.py`, `service/lost_reports.py`, `router/found_items.py`, `router/lost_reports.py`, 해당 요청/응답/쿼리 schema와 계약 테스트. 공통 소유 영역: `schema/matching.py`, `schema/matching_params.py`, `library/matching_lock.py`, `library/protected_http.py`, 이후 `service/text_analysis.py`·`service/matching.py`·워커. 충돌이 나면 기존 변경을 덮어쓰지 않고 이 경계에 맞춰 연결한다.

## 명세 검토와 변경 방향

계획 수립 시 [API 목록](../api/README.md), [공통](../api/00-common.md), [습득물](../api/02-found-items.md), [분실 신고·매칭](../api/03-lost-reports-matching.md), [알림](../api/04-profile-notifications.md), [수거](../api/05-collection-disputes-messages.md), [관리자](../api/06-admin.md)를 확인했다. 구현 계획 변경 시에도 다시 대조한다.

기존 경로·HTTP 메서드·소유권·CSRF·페이지·정렬은 유지한다. 원문 토큰 비교는 번역 후 canonical 키워드 비교로 바꾼다. 상태 응답을 추가하고 수거의 409 MATCHING_PENDING을 명시한다. 일반 검색·키워드 구독은 변경하지 않는다. 관련 API 문서에 비동기 계약과 응답 필드를 추가한다. 후보 조회는 여전히 부작용이 없다.

## 1단계 제공 계약

- `schema.matching.ProcessingStatus`: PENDING / PROCESSING / READY / FAILED. 내부 SUPERSEDED는 API에 노출하지 않는다.
- `TextAnalysisProgress`: analysisStatus 필수. FoundItemDetail에 상속 또는 동일 필드 구성으로 포함한다. 다른 사람의 신고 집계 상태는 공개 물품 응답에 넣지 않는다.
- `MatchingProgress`: analysisStatus + matchingStatus 필수. LostReportResponse 및 private 필드를 제외한 Summary에 포함한다.
- `MatchCandidatePage`: 기존 페이지·후보 정보 + analysisStatus + matchingStatus + isComplete. 필드는 필수이며 PENDING 기본값으로 완료 상태를 숨기지 않는다.
- `schema.matching_params.MatchingParams`: page=0, size=20, 최대100, extra 금지.
- `library.matching_lock.lock_matching_categories(db, category_ids)`: UUID 집합을 받아 호출자가 연 트랜잭션 안에서만 잠금. commit/rollback하지 않는다.
- `ProtectedRoute`: 선언된 body 모델이 있는 쓰기는 기존 JSON 검증을 유지한다. body 모델 없는 쓰기는 빈 본문·Content-Type 생략을 허용하고, 실제 비어 있지 않은 본문(예: `{}`)은 400 VALIDATION_ERROR다. 두 경우 모두 인증·Origin·CSRF 검사를 먼저 수행한다.

진행 상태 의미: PENDING은 작업 대기, PROCESSING은 실행 또는 최신 집합 재평가 진행, READY는 해당 범위 완료, FAILED는 현재 범위의 실패다. matchingStatus는 신고 자신의 분석뿐 아니라 현재 비교 범위의 미완료·실패도 반영한다. 실패가 하나라도 있으면 FAILED, 없으면 PROCESSING, PENDING, READY 순으로 집계한다. READY에만 isComplete=true다. 처리 중 페이지 개수는 현재 유효한 후보 집합 기준이며 최종 개수가 아니다.

종료 신고는 분석/매칭 작업을 새로 만들지 않고 보존된 후보 이력을 제공한다. 이력 조회의 matchingStatus=READY, isComplete=true는 과거 보존 목록 조회가 완료됐다는 의미다. analysisStatus는 마지막 보존 분석 상태를 유지한다. 숨김·삭제와 권한 필터는 이력에도 적용한다. 번역문·키워드·오류 내부 정보·모델 경로는 응답하지 않는다.

## 4단계 트랜잭션 연결 규약

ProtectedRoute가 제공하는 request.state.db/user/now를 사용하고 서비스에서 중간 commit을 하지 않는다. API 요청 중 번역을 호출하거나 워커 완료를 기다리지 않는다.

1. 인증·입력 검증 후 기존 원본을 읽어 관련 카테고리 스냅샷을 확보한다.
2. 새 카테고리와 이전 카테고리 잠금을 한 번에 얻는다. 물품/신고 행을 먼저 잠그지 않는다.
3. 원본 행을 잠그고 스냅샷의 category_id가 여전히 같은지 재확인한다. 달라졌으면 트랜잭션 전체를 중단해 재시도한다. 추가 카테고리 잠금을 임의로 뒤늦게 얻지 않는다.
4. 상태·소유권·참조를 검사하고 원본/건물 연결/사진/비공개 정보를 저장한다.
5. flush 후 DB 트리거가 만든 text_version과 ORM version을 사용해 분석·재평가 요청을 연결한다.
6. 원본·분석 PENDING·outbox·재평가 generation·감사를 같은 트랜잭션으로 커밋한다. 요청 생성 실패 시 원본만 남기는 커밋을 하지 않는다.

잠금 순서: ProtectedRoute의 역할·세션/사용자 잠금 → 정렬된 카테고리 잠금 → 물품 UUID 순 → 신고 UUID 순 → 분석/후보/작업 행. 워커는 역할/세션 잠금을 획득하지 않는다. 같은 트랜잭션에서 필요한 카테고리 잠금을 호출별로 나누어 얻지 않는다.

카테고리 키는 UUID의 SHA-256 앞 4바이트 signed int와 고정 namespace(2-int advisory key space)를 사용하며 정렬은 실제 key 기준이다. 해시 충돌은 불필요한 직렬화만 늘리고 누락을 만들지 않는다. lock timeout·교착·직렬화 실패는 전체 트랜잭션 재시도 또는 공통 CONCURRENT_MODIFICATION 응답으로 처리한다.

## 3단계에서 제공할 내부 함수 계약 — 아직 미구현

아래 이름을 연결 지점으로 예약한다. 4단계에서 동일 파일을 별도 구현하거나 빈 성공 stub으로 대체하지 않는다. 함수가 준비되기 전 원본 API를 운영 완료로 표시하지 않는다.

```python
async def request_found_item_analysis(db, *, item, now): ...
async def request_lost_report_analysis(db, *, report, now): ...
async def request_item_reevaluation(db, *, item, now): ...
async def request_report_reevaluation(db, *, report, now): ...
```

위 함수는 `service/text_analysis.py`에서 제공하며 트랜잭션·카테고리 잠금은 호출자 소유다. 함수는 commit·모델 호출을 하지 않는다. 검증된 활성 정책·프로필을 확인하고 idempotent UPSERT한다. 분석 요청 함수는 현재 text_version의 분석 행과 feature ID 기반 outbox를 보장하고 재평가도 요청한다. 재평가 전용 함수는 번역을 다시 만들지 않고 requested_generation만 증가시킨다. API DTO 생성은 원본 서비스가 담당하며 진행 상태 조회의 구체 함수는 3단계 구현 시 추가 문서화한다.

이벤트 타입은 FOUND_ITEM_TEXT_ANALYSIS_REQUESTED / LOST_REPORT_TEXT_ANALYSIS_REQUESTED. aggregate_id=분석 행 UUID, aggregate_version=1. payload는 featureId, itemId 또는 reportId, profileId, textVersion만 허용한다. 원문·private details·번역문·키워드는 복제하지 않는다.

활성 프로필이 아직 없는 상태의 등록 동작은 3단계에서 명세와 함께 확정한다. 유효한 프로필 없이 임의 profile ID를 넣거나 READY를 반환하지 않는다. source_language는 현재 DB에서 KO/EN/MIXED만 허용하므로 미지원 언어의 실패 기록 표현도 2~3단계에서 결정한다. 이 두 항목은 원본 API의 최종 통합 전 해결해야 한다.

## 변경 종류별 요청

| 변경 | 처리 |
| --- | --- |
| 신규 원본 | 분석 요청 + 재평가 |
| 습득물 제목/공개 설명, 신고 공개 설명 변경 | 증가한 text_version 분석 요청 + 재평가 |
| 카테고리·발견일·가능 건물 변경 | 분석 재사용, 재평가 |
| privateIdentifyingDetails만 변경 | 번역 금지. 기존 version 변경에 따른 후보 검증을 위해 재평가 |
| 연장 | 번역 재사용. version 변경 시 재평가하고 만료 경합 재확인 |
| 재등록 | 번역 재사용, 현재 상태와 정책으로 재평가 |
| 신고 종료 | private 즉시 삭제, 대기 분석/재평가 종료, 신규 알림 억제. 기존 READY 분석·후보 이력은 유지 |
| 물품 논리 삭제 | DB 트리거가 분석·재평가·후보 제거 및 분석 outbox 취소. 메시지·기타 보존은 기존 명세 준수 |

미완료 분석 결과는 양쪽 버전·정책·lease를 검증하기 전 저장하지 않는다. 기존 건물 OR 키워드 규칙과 KST 날짜 하한을 유지하고 lostDateTo 상한을 추가하지 않는다.

## API 담당자가 함께 구현해야 할 기존 규칙

- 물품: 작성자/상태 검사, 사진 1~5장과 소유권·purpose·alt 검증, 보관 방식·이력, 민감 라벨과 열람 감사, 논리 삭제·재등록 규칙. 사진 연결은 기존 service/photo_attachments.py를 재사용한다.
- 신고: 본인만 쓰기, 관리자 읽기만 허용, PUT 전체 교체, 가능한 건물 1~100개·날짜·기존 비활성 참조 유지, 30일 만료/연장, private 생성·종료 삭제·종료 후 재개방 금지.
- no-store, Content-Language, Location, KST, 오류 은닉 404와 기존 필드 모델 유지.
- 원본 응답·목록에는 private/사진 URL/번역 결과가 잘못 섞이지 않도록 DTO를 분리한다.

## 후속 단계의 통합 지점과 검증

관리자 숨김·만료·수거 경로도 카테고리 잠금 규약에 참여해야 한다. 현재 공통 helper만 추가한 상태이며 기존 admin 서비스가 자동으로 새 규약을 지키는 것은 아니다. 6단계에서 관련 명세를 재확인하고 연결한다.

수거는 필요한 최신 분석 미완료 시 409 MATCHING_PENDING으로 원자적 거절한다. 최신 후보 확인 후 수거자 자신의 연결된 OPEN 신고 전부만 종료한다. 외부 이메일 제공자 설정과 실제 전송 검증은 별도이며, 인앱·이메일 예약의 원자성 및 중복 억제는 6단계 책임이다.

1단계 검증은 상태 모델·페이지·OpenAPI, 본문 없는 POST/DELETE의 인증/CSRF/Origin/빈 본문/불필요 본문, 기존 JSON 쓰기 회귀, 실제 PostgreSQL 카테고리 잠금의 순서·유지·해제다. 후속 단계는 실제 번역·lease 경합·양쪽 동시 분석·삭제 후 늦은 완료·알림 중복·수거와 변경 경합을 검사한다. 실행은 기존 backend 컨테이너 /app, 테스트는 전용 kaifind_test_* DB와 kaifind-test-* 버킷만 사용한다.

## 1단계 적용 결과

2026-11-08: schema/matching.py·matching_params.py, library/matching_lock.py를 추가하고 ProtectedRoute의 body 모델 유무에 따른 검증·OpenAPI와 잠금 타임아웃의 409 CONCURRENT_MODIFICATION 처리를 반영했다. MATCHING_PENDING의 한영 오류 문구를 추가했다. 기능 라우터·원본 서비스·DB 스키마는 변경하지 않았다.

기존 backend 컨테이너 /app에서 별도 kaifind_test_matching_contract_20261108 DB로 전체 테스트 363개가 통과했다. 이후 실제 잠금 타임아웃·MATCHING_PENDING 한영 오류 3개를 추가하고 관련 테스트 19개가 통과했다(전체 고유 테스트 366개). 수정한 습득물·신고 명세의 모든 JSON 예시도 파싱 검증했다. 모델 런타임·분석 요청 함수·진행 상태 집계·MATCH-01 라우터와 원본 API의 실제 연결은 아직 구현/검증하지 않았다. 기존 pytest-asyncio의 fixture loop scope 경고는 이번 범위에서 변경하지 않았다.
