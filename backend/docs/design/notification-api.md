# Notification API 설계

작성: 2026-11-09 KST. **설계 문서이며 구현 완료를 뜻하지 않는다.**

2026-11-09 구현: NOTI-01~04의 schema·서비스·라우터를 연결했다. 이벤트 생산·이메일 전달·rate limit은 후속 과제다.
기존 DB가 허용하는 관련 ID 없는 알림은 해당 종류의 목록 화면(`/lost-reports` 또는 `/found-items`)으로 이동한다.

[API 목차](../api/README.md), [공통 계약](../api/00-common.md),
[프로필·알림 명세](../api/04-profile-notifications.md),
[DB 설계](../db/README.md), [매칭 구현](matching-api.md)을 기준으로 한다.
NOTI-01~04의 경로·모델·인증 계약을 유지한다. 프로필·키워드 구독 CRUD는 이번 설계의 구현 범위 밖이며,
KEYWORD_MATCH 생산자는 해당 기능과 연결할 때 구현한다. 수거·만료 생산자도 각 도메인의 실제 트랜잭션에 연결해야 한다.

## 공개 API

Base path는 `/api/v1`이다. 모든 API는 세션 사용자 본인만 접근하며 ADMIN도 타인의 알림을 조회하지 못한다.
`ProtectedRoute`로 세션, 쓰기 CSRF·Origin, JSON·오류 계약을 적용한다.
응답은 공통 wrapper 없이 모델을 직접 반환하고 `Cache-Control: no-store`, `Content-Language`를 제공한다.
시각은 RFC3339 KST, ID는 UUID다.

| ID | Method / path | 입력 | 성공 |
| --- | --- | --- | --- |
| NOTI-01 | GET `/me/notification-settings` | 없음 | 200 NotificationSettingsResponse |
| NOTI-02 | PUT `/me/notification-settings` | UpdateNotificationSettingsRequest | 200 NotificationSettingsResponse |
| NOTI-03 | GET `/me/notifications` | NotificationParams | 200 NotificationPage |
| NOTI-04 | PATCH `/me/notifications/{notificationId}` | UpdateNotificationRequest | 200 NotificationResponse |

인앱 생성·메일 발송·워커 재시도용 회원 API는 만들지 않는다. 전체 읽음·삭제·미확인 개수 전용 API도 이번 범위에 추가하지 않는다.

### 설정 조회·교체

두 설정 모델은 아래 다섯 필드를 사용한다. 모두 필수 boolean이고 null·문자열·정수·미정의 필드는 거부한다.

```json
{
  "emailEnabled": true,
  "matchEmail": true,
  "collectionEmail": true,
  "expiryEmail": true,
  "keywordEmail": true
}
```

- 저장 행이 없으면 GET은 모두 true를 반환하며 DB를 변경하지 않는다. 발송 검사도 같은 기본값을 사용한다.
- PUT은 전체 교체다. user_id 유일 키로 원자적 UPSERT하고 저장 결과를 반환한다. 일부 누락은 400이다.
- 동시 PUT은 DB에서 직렬화된 마지막 쓰기를 반영한다. 버전 조건이나 필드 단위 병합은 제공하지 않는다.
- 전체 허용 AND 해당 종류 허용일 때만 이메일 대상이다. 인앱 생성에는 영향을 주지 않는다.
- off 상태에서 생성되었거나 발송 전 수신 거부로 취소된 이메일은 다시 on으로 바꿔도 소급 발송하지 않는다.
  이는 기존 명세의 수신 거부 처리를 구체화한 설계 선택이다.

### 목록 조회

| query | 타입 | 기본값 / 범위 |
| --- | --- | --- |
| page | integer | 0 / 0 이상 |
| size | integer | 20 / 1~100 |
| unreadOnly | boolean | false / true이면 read_at IS NULL |

알 수 없는 query, 잘못된 UUID·페이지·boolean 표현은 공통 검증 규칙에 따라 400이다.
boolean query는 프로젝트 공통 파서와 허용 표현을 맞추며 JSON boolean의 엄격 검증과 구분한다.

조회 조건은 `recipient_id = session.user.id`이며 `unreadOnly=true`이면 미확인 조건을 추가한다.
보존기간이 끝난 행은 정리 배치 지연 중에도 `purge_after > request.state.now` 조건으로 제외한다.
정렬은 `created_at DESC, id DESC`다. 목록과 개수는 동일 statement snapshot의 CTE로 조회한다.
빈 결과와 범위 밖 페이지도 요청 page·size 및 전체 개수를 반환하며, 전체가 0이면 totalPages=0이다.
offset 방식이므로 서로 다른 요청 사이에 새 알림이 생기면 페이지 위치가 바뀔 수 있다.

NotificationResponse의 모든 키를 반환한다.

| 필드 | 타입 | 규칙 |
| --- | --- | --- |
| notificationId | UUID | 알림 ID |
| type | enum | MATCH_CANDIDATE / ITEM_COLLECTED / ITEM_EXPIRED / KEYWORD_MATCH |
| message | string | Accept-Language에 따른 고정 안내 문구 |
| targetPath | string | 아래 허용된 UI 상대 경로 |
| itemId | UUID 또는 null | 관련 물품 |
| reportId | UUID 또는 null | 매칭 신고. 다른 종류는 null |
| createdAt | date-time | 생성 시각 |
| readAt | date-time 또는 null | 최초 확인 시각 |

| 종류 | 수신자 | targetPath | 한국어 문구 |
| --- | --- | --- | --- |
| MATCH_CANDIDATE | 신고 작성자 | `/lost-reports/{reportId}/matches` | 분실 신고와 일치할 수 있는 습득물이 등록되었습니다. |
| ITEM_COLLECTED | 습득물 작성자 | `/found-items/{itemId}` | 등록한 습득물의 수거가 완료되었습니다. |
| ITEM_EXPIRED | 습득물 작성자 | `/found-items/{itemId}` | 등록한 습득물의 보관 기간이 만료되었습니다. |
| KEYWORD_MATCH | 구독자 | `/found-items/{itemId}` | 구독한 키워드와 일치하는 습득물이 등록되었습니다. |

UI 경로는 API 경로가 아니며 프런트엔드 라우팅과 통합 시 확인한다. 영문 고정 문구도 같은 종류별 키로 관리한다.
제목·본문·민감도·사진·보관 위치·타인 연락처를 조합하거나 저장하지 않는다.
숨김·종료 뒤에도 이미 생성된 일반 안내는 이력으로 유지한다. 상세 화면은 별도 권한 검사로 접근을 막는다.
영구 삭제는 기존 FK CASCADE를 따르며, 이력 유지가 대상 상세 접근 권한을 부여하지 않는다.

### 읽음 처리

본문은 `{"read": true}`만 허용한다. false, null, 누락, 추가 필드는 400이다.
수신자·ID·보존기간 조건으로 UPDATE하고 `read_at = COALESCE(read_at, now)`를 사용한다.
RETURNING 결과로 응답을 만들며, 동시·반복 요청에도 최초 readAt을 유지한다.
존재하지 않거나 타인의 알림, 보존기간이 지난 알림은 모두 404 NOTIFICATION_NOT_FOUND다.
읽음 처리는 이메일 취소 조건이 아니다.

### 오류

공통 ErrorResponse(`code`, `message`, `fieldErrors`)를 사용한다.
400 VALIDATION_ERROR/MALFORMED_JSON, 401 AUTH_REQUIRED/SESSION_EXPIRED,
403 CSRF_INVALID/ORIGIN_NOT_ALLOWED, 415 UNSUPPORTED_MEDIA_TYPE, 500 INTERNAL_SERVER_ERROR를 적용한다.
읽음 처리에는 404 NOTIFICATION_NOT_FOUND를 추가한다. GET에는 JSON 본문을 요구하지 않는다.
인증·입력 검사 순서는 기존 ProtectedRoute를 따른다.

## 이벤트 생산과 중복 방지

1. 도메인 변경과 알림 의도를 같은 DB 트랜잭션에 기록한다. 원본만 커밋한 뒤 메모리 작업으로 알림을 만들지 않는다.
2. 매칭은 기존 카테고리 → 물품 → 신고 → 후보 잠금 순서를 지킨다. 현재 정책·양쪽 version·후보 active,
   신고 OPEN·미만료, 물품 POSTED·미숨김·미삭제를 재검사한다. building 후보는 분석 완료를 기다릴 필요가 없다.
3. 후보 행을 잠근 상태에서 first_notified_at이 null일 때 인앱·이메일 항목과 최초 통지 시각을 함께 저장한다.
   매칭 event_id는 candidate.id를 사용한다. 재평가·비활성 후 재등장에도 새 event_id를 만들지 않는다.
   여기서 최초 통지 시각은 이메일 전송 완료가 아니라 인앱 생성 시각이다.
4. 수거·만료·키워드는 각각 안정적인 논리 outbox event UUID를 사용한다. 수거 취소 후 다시 수거된 사건은 새 이벤트다.
   outbox aggregate_id/version/type의 유일 키는 생산자 원본 버전과 함께 정의하고 재처리 중 변경하지 않는다.
5. 소비자는 notifications의 UNIQUE(event_id, recipient_id, type)과 email_delivery_items의
   UNIQUE(notification_id)로 멱등성을 확보한다. outbox processed_at도 같은 트랜잭션에서 기록한다.
   매칭은 후보 트랜잭션에서 직접 생성하므로 별도의 매칭 알림 outbox 없이 원자성을 확보할 수 있다.

최초 알림을 만들 때 이메일 수신이 허용된 경우에만 PENDING 항목을 만든다.
인앱·메일 항목 중 일부만 저장되거나 first_notified_at만 남는 커밋은 허용하지 않는다.
기존 first_notified_at이 있는 후보는 재통지하지 않는다. 기존 인앱/메일 항목이 없는 이력을 소급 보완할지는
운영 이행 정책으로 분리하며 자동 backfill하지 않는다.

분석 outbox 소비자는 현재 분석 event_type만 처리한다. 알림 소비자도 자신의 event_type 허용 목록만 claim하며,
같은 processed_at을 서로 다른 소비자가 공동으로 완료 표시하지 않는다.

## 이메일 전달

이 부분은 NOTI API의 후속 내부 처리다. API 구현 완료와 전달 시스템 완료를 구분한다.

- 기존 email_deliveries·email_delivery_items를 영속 큐로 사용한다. 수신 이메일은 전송 시 본인 계정에서 조회한다.
- 개별 슬롯 1~19, 요약 슬롯 20, KST 20:00 요약은 기존 제안값을 유지한다.
  수신자 행 잠금·UNIQUE(recipient_id, delivery_date, slot_no)로 경합을 제어한다.
  요약 마감 후 초과분은 다음 저녁으로 이월하고, 빈 요약은 발송하지 않는다.
- 다음 날짜 재시도는 실제 발송일의 슬롯으로 원자적 재예약한다. 같은 논리 delivery ID를 유지한다.
  그날 슬롯이 없으면 이월하며, 요약 편입 항목을 두 delivery에 동시에 연결하지 않는다.
- 발송 직전 설정, 신고 OPEN·미만료, 물품 접근 가능성, 키워드 구독 근거를 재검사한다.
  수거·만료 알림은 COLLECTED/EXPIRED 자체가 발송 사유이므로 POSTED 조건을 일괄 적용하지 않는다.
  취소된 수거의 미발송 메일 등 사건 유효성도 종류별로 확인한다.
- 제외된 항목은 CANCELLED, 전송 성공만 SENT다. 일시 실패는 RETRY,
  영구 오류는 FAILED로 남기고 운영자가 식별·재시도할 수 있게 한다.
- 재시도 간격은 기존 1분·5분·30분 제안을 출발점으로 상한과 jitter를 설정한다.
  장기 장애는 느린 재시도와 운영 경보 대상으로 두고 성공으로 버리지 않는다.
- 외부 호출 동안 DB 잠금을 유지하지 않는다. 전송 직전 검사가 끝난 뒤 설정·상태가 바뀌어 이미 진행 중인
  외부 발송을 회수할 수 없는 경계는 인정한다. 본문은 일반 안내·인증이 필요한 링크만 포함한다.
- provider idempotency key는 delivery.id다. 타임아웃으로 결과가 불명확하면 제공자 상태를 먼저 확인한다.
  제공자 지원이 없으면 정확히 한 번 전달을 보장할 수 없으며 무조건 성공 처리하지 않는다.

## 파일 배치와 DB 보완

| 파일·영역 | 책임 |
| --- | --- |
| router/notifications.py | 기존 501 교체, ProtectedRoute·요청/응답 모델·서비스 연결 |
| schema/notifications.py | 설정·읽음 요청, NotificationResponse·NotificationPage |
| schema/notification_params.py | NotificationParams Pydantic query 모델 |
| service/notifications.py | 본인 설정 UPSERT·목록·읽음, 종류별 안전한 DTO 생성 |
| service/notification_events.py | 호출자 트랜잭션 안에서 생성·중복 억제. 자체 commit 금지 |
| service/notification_worker.py | 알림 outbox event_type 전용 소비·복구 |
| service/email_worker.py | 슬롯 예약·요약·제공자 연동·재시도 |
| 기존 matching/수거/만료 서비스 | 잠금·상태 변경 트랜잭션에 생산자 연결 |
| 앱 lifespan·설정 | 기존 backend 안에서 소비자 시작·종료, 메일 제공자·테스트 수신함 구성 |

HTTP API 4개에는 기존 테이블·인덱스로 충분하다. 다섯 설정 기본값과 보존기간 필터를 서비스에서 일치시킨다.
메일 워커 구현 전에는 별도 Alembic revision으로 email_deliveries.lease_token UUID를 추가하는 설계를 적용한다.
현재 모델에는 lease_until만 있어 만료된 이전 워커의 늦은 저장을 확실히 차단하기 어렵다.
claim마다 새 token을 만들고 token·유효 lease 조건으로 완료/실패를 갱신한다.
이는 현재 DB 모델에 대한 명시적 보완 제안이며 이번 문서 작업에서 migration을 실행하지 않는다.
외부 발송 중복은 fencing만으로 해결되지 않으므로 provider idempotency도 함께 필요하다.

## 구현 순서와 검증 기준

1. schema·서비스·라우터로 NOTI-01~04를 구현하고 HTTP/OpenAPI 검증을 마친다.
2. 매칭의 원자적 최초 알림 생성과 수거·만료 outbox 생산자/소비자를 연결한다.
3. 메일 lease 보완, 제공자 어댑터, 한도·요약·실패 복구를 구현한다.
4. 키워드 구독 구현 시 등록 이벤트·다중 구독 근거와 구독 해제를 연결한다.

필수 검증은 아래와 같다.

- 미인증 401, CSRF/Origin, 본인·타인·관리자 권한, 미정의 필드·query·null·타입 오류.
- 기본 설정 GET 전후 DB 불변, PUT 전체 교체·동시 최초 UPSERT, 이메일 off 중 인앱 유지.
- 미확인 필터·고정 정렬·빈/범위 밖 페이지·동일 snapshot 개수, ko/en·KST·no-store.
- 최초/반복/동시 읽음의 readAt 유지, 타인·없는·보존 만료 ID의 동일 404.
- 후보 양쪽 워커 경합·재등장·원본 종료/숨김·트랜잭션 롤백 시 중복/유실 방지.
- 분석 소비자와 알림 소비자가 서로의 outbox를 claim하지 않음.
- 19통 경계·20시 경계·KST 자정·동시 슬롯·다음 날 재예약·빈 요약·구독 해제/수신 거부.
- lease 만료·오래된 워커 완료 거부·provider 성공 후 DB 기록 실패·결과 불명확 타임아웃 복구.
- 응답·메일·payload·로그에 사진·위치·비공개 식별 정보·타인 연락처가 없음.

실행 검증은 기존 backend 컨테이너 `/app`에서만 수행한다. DB는 기존 db의 별도 kaifind_test_*를 사용하고
메일은 목업/테스트 수신함을 사용한다. 실제 제공자 전달·운영 부하·프런트엔드 라우팅은 별도 통합 검증 대상이다.

2026-11-09 검증: 기존 backend `/app`에서 별도 테스트 DB로 알림 32개와 인증·프로필·ProtectedRoute 회귀를
포함한 총 142개 테스트가 통과했다. `git diff --check`도 통과했다.
기존 pytest-asyncio fixture loop scope deprecation 경고가 남아 있다.
추가 검증: 알림 HTTP·모델 테스트를 보강하여 두 파일의 90개 테스트가 통과했다.
종류별 한영 문구·안전한 응답 필드·세션 만료·조회 부작용 없음·실패 시 데이터 보존과 엄격 boolean을 포함한다.
이벤트 생산·메일 전달·rate limit·실제 부하와 프런트엔드 라우팅은 미검증이다.
