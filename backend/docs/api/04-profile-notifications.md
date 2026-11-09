# 프로필·알림·키워드 구독

> 원문: [Notion](https://app.notion.com/p/40c23542cf8c81cb8607f7c083453384?pvs=204) · 내보낸 날짜: 2026-11-02 (KST)

## 범위와 공통 계약

2026-11-09: [Notification API 구현 설계](../design/notification-api.md)에 NOTI-01~04의 저장·조회·동시성, 매칭 최초 알림과 이메일 전달 통합을 구체화했다. 기존 공개 계약을 유지하며 추가 설계 선택·DB 보완 제안과 미검증 범위를 별도로 표시한다.

SRS FR-4 프로필·이메일 종류별 설정(Should), FR-17 매칭 알림(Must), FR-18 키워드 구독(Could), FR-19 일일 한도·요약(Should), FR-20 수거 알림·FR-25 만료 알림(Must), REL-2 재시도, USA-3 언어 전환을 다룬다. 우선순위가 낮은 구독·요약 API도 설계하되 Must 알림을 제거하지 않는다.

경로·모델·문자수·메일 한도·요약 시각은 설계 초안이다. [인증](01-auth.md)의 세션·CSRF·오류 계약을 공통 적용한다. 개인 정보의 공개 프로필 API는 제공하지 않는다.

### 요청·응답 형식

| 항목 | 규칙 |
| --- | --- |
| Base URL | /api/v1 |
| 본문 | JSON 요청은 application/json. GET·본문 없는 DELETE에는 본문을 보내지 않음 |
| 언어 | Accept-Language: ko 또는 en. 기본 ko. Content-Language 반환 |
| 캐시 | Cache-Control: no-store |
| 시간·ID | UUID, RFC3339 +09:00. 언어 ko/en |

### 인증·권한·적용 범위

| 항목 | 규칙 |
| --- | --- |
| 공통 권한 | 현재 인증된 사용자 본인만. 관리자도 이 경로에서 타인 설정·알림을 조회하지 못함 |
| 인증 | KAIFIND\_SESSION 쿠키. 쓰기 요청은 X-CSRF-Token 필수 |
| 요청 검증 | 미정의 필드·null·타입 오류 거부. trim 후 문자열 길이 검사 |

### 오류 처리

| 항목 | 규칙 |
| --- | --- |
| ErrorResponse | code: string; message: string; fieldErrors: FieldError 배열 |
| FieldError | field: string; code: string; message: string. 필드 오류가 없으면 빈 배열 |
| HTTP 400 | <code>MALFORMED_JSON / VALIDATION_ERROR</code> |
| HTTP 401 | <code>AUTH_REQUIRED / SESSION_EXPIRED</code> |
| HTTP 403 | <code>CSRF_INVALID / ORIGIN_NOT_ALLOWED</code> |
| HTTP 415 | <code>UNSUPPORTED_MEDIA_TYPE</code> |
| HTTP 500 | <code>INTERNAL_SERVER_ERROR</code> |

### 목록·페이지네이션

| 항목 | 규칙 |
| --- | --- |
| 페이지네이션 | items,page,size,totalElements,totalPages. page 기본0, size 기본20·최대100 |

## 엔드포인트 목록

### 프로필

| ID | Method | Endpoint |
| --- | --- | --- |
| PROFILE-01 | GET | <code>/me/profile</code> |
| PROFILE-02 | PATCH | <code>/me/profile</code> |

| ID | Request model | 성공 |
| --- | --- | --- |
| PROFILE-01 | 없음 | 200 ProfileResponse |
| PROFILE-02 | UpdateProfileRequest | 200 ProfileResponse |

### 알림

| ID | Method | Endpoint |
| --- | --- | --- |
| NOTI-01 | GET | <code>/me/notification-settings</code> |
| NOTI-02 | PUT | <code>/me/notification-settings</code> |
| NOTI-03 | GET | <code>/me/notifications</code> |
| NOTI-04 | PATCH | <code>/me/notifications/{notificationId}</code> |

| ID | Request model | 성공 |
| --- | --- | --- |
| NOTI-01 | 없음 | 200 NotificationSettingsResponse |
| NOTI-02 | UpdateNotificationSettingsRequest | 200 NotificationSettingsResponse |
| NOTI-03 | 없음 | 200 NotificationPage |
| NOTI-04 | UpdateNotificationRequest | 200 NotificationResponse |

### 키워드 구독

| ID | Method | Endpoint |
| --- | --- | --- |
| KEYWORD-01 | GET | <code>/me/keyword-subscriptions</code> |
| KEYWORD-02 | POST | <code>/me/keyword-subscriptions</code> |
| KEYWORD-03 | DELETE | <code>/me/keyword-subscriptions/{subscriptionId}</code> |

| ID | Request model | 성공 |
| --- | --- | --- |
| KEYWORD-01 | 없음 | 200 KeywordSubscriptionPage |
| KEYWORD-02 | CreateKeywordSubscriptionRequest | 201 KeywordSubscriptionResponse |
| KEYWORD-03 | 없음 | 204 No Content |

## PROFILE-01 내 프로필 조회

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/me/profile |
| 접근 | 인증된 본인(MEMBER 또는 ADMIN) |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 ProfileResponse |
| 실패 | 공통 오류 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | Accept-Language | string | 아니오 | ko 또는 en, 기본 ko |

### 처리 규칙

- 로그인한 본인의 사용자 정보를 반환한다. 인증의 AuthUserResponse와 동일한 필드 구조를 사용한다.
- 이메일은 본인에게만 제공한다. 타 회원 조회에 이 DTO를 재사용하지 않는다.
- 공개 프로필·사용자 검색 기능은 이 범위에 추가하지 않는다.

## PROFILE-02 언어 설정 변경

| 항목 | 내용 |
| --- | --- |
| Method / URL | PATCH /api/v1/me/profile |
| 접근 | 인증된 본인(MEMBER 또는 ADMIN) |
| Request body | JSON |
| Request model | UpdateProfileRequest |
| 성공 | 200 ProfileResponse |
| 실패 | 공통 오류 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | string | 아니오 | ko 또는 en, 기본 ko |

### 처리 규칙

- 변경 가능한 필드는 language 하나다. SSO 제공 name·email·affiliation과 role·userId는 받지 않는다.
- 저장된 언어는 다음 프로필·auth/me 조회에도 동일하게 보인다.
- 화면 언어는 즉시 전환할 수 있어야 한다. 비회원은 클라이언트 설정과 Accept-Language를 이용하므로 로그인을 강제하지 않는다.
- 이름·전화번호·자기소개 등 SRS에 없는 개인정보 입력을 추가하지 않는다.

### Request body 예시

```json
{
  "language": "en"
}
```

## NOTI-01 이메일 알림 설정 조회

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/me/notification-settings |
| 접근 | 인증된 본인(MEMBER 또는 ADMIN) |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 NotificationSettingsResponse |
| 실패 | 공통 오류 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | Accept-Language | string | 아니오 | ko 또는 en, 기본 ko |

### 처리 규칙

- 기본값은 모든 값 true다. 이메일을 끄지 않은 회원에게 신규 매칭 이메일이 전송되도록 한다.
- 인앱 알림은 이 설정과 무관하게 유지한다.

## NOTI-02 이메일 알림 설정 변경

| 항목 | 내용 |
| --- | --- |
| Method / URL | PUT /api/v1/me/notification-settings |
| 접근 | 인증된 본인(MEMBER 또는 ADMIN) |
| Request body | JSON |
| Request model | UpdateNotificationSettingsRequest |
| 성공 | 200 NotificationSettingsResponse |
| 실패 | 공통 오류 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | string | 아니오 | ko 또는 en, 기본 ko |

### 처리 규칙

- 다섯 boolean을 모두 전달한다. 일부만 전달하면 400. 동일 값 재요청은 현재 설정을 반환한다.
- emailEnabled=false는 전체 이메일 수신 거부. 특정 종류 플래그 false는 해당 종류만 거부한다.
- 발송 직전에 현재 설정을 재확인한다. 이미 큐에 들어간 알림·요약도 수신 거부한 종류를 제외한다.
- 설정 변경은 인앱 알림·후보 계산·수거 처리를 중단하지 않는다.

### Request body 예시

```json
{
  "emailEnabled": true,
  "matchEmail": true,
  "collectionEmail": true,
  "expiryEmail": true,
  "keywordEmail": true
}
```

## NOTI-03 내 알림 목록

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/me/notifications |
| 접근 | 인증된 본인(MEMBER 또는 ADMIN) |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 NotificationPage |
| 실패 | 공통 오류 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | Accept-Language | string | 아니오 | ko 또는 en, 기본 ko |
| query | page | integer | 아니오 | 기본0, 0 이상 |
| query | size | integer | 아니오 | 기본20, 1\~100 |
| query | unreadOnly | boolean | 아니오 | 기본 false. true면 미확인 알림만 |

### 처리 규칙

- 수신자 ID는 세션에서 결정한다. 임의 사용자 ID는 받지 않는다.
- createdAt 내림차순, 동률 notificationId 내림차순으로 반환한다.
- 매칭·수거·만료·키워드 이벤트는 이메일 설정과 관계없이 인앱 목록에 기록한다.
- 민감 사진·보관 위치·다운로드 URL·분실 신고 비공개 정보·타인 연락처는 알림 payload에 넣지 않는다.
- 알림은 관련 화면의 내부 상대 경로만 가진다. 이동한 화면에서도 다시 리소스 권한을 검사한다. 삭제·숨김된 대상의 상세는 조회 불가할 수 있다.

## NOTI-04 알림 확인 처리

| 항목 | 내용 |
| --- | --- |
| Method / URL | PATCH /api/v1/me/notifications/\{notificationId\} |
| 접근 | 인증된 본인(MEMBER 또는 ADMIN) |
| Request body | JSON |
| Request model | UpdateNotificationRequest |
| 성공 | 200 NotificationResponse |
| 실패 | 공통 오류, 404 NOTIFICATION\_NOT\_FOUND |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | string | 아니오 | ko 또는 en, 기본 ko |
| path | notificationId | string(UUID) | 예 | 본인의 알림 ID |

### 처리 규칙

- 본인 알림만 읽음 처리한다. 타인 또는 없는 알림은 404.
- read=true만 허용한다. 최초 확인 시 readAt을 기록하고 반복 요청 시 최초 시각을 유지한다.
- 이 기능은 마이페이지 편의를 위한 설계 추가다. 읽음 처리는 이메일 취소나 매칭 취소를 의미하지 않는다.

### Request body 예시

```json
{
  "read": true
}
```

## KEYWORD-01 내 키워드 구독 목록

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/me/keyword-subscriptions |
| 접근 | 인증된 본인(MEMBER 또는 ADMIN) |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 KeywordSubscriptionPage |
| 실패 | 공통 오류 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | Accept-Language | string | 아니오 | ko 또는 en, 기본 ko |
| query | page | integer | 아니오 | 기본0, 0 이상 |
| query | size | integer | 아니오 | 기본20, 1\~100 |

### 처리 규칙

- 본인 구독만 반환한다. createdAt 내림차순, 동률 subscriptionId 내림차순.
- 키워드 구독은 Could 기능이다. 기능을 제외하더라도 FR-17 매칭 알림은 유지해야 한다.

## KEYWORD-02 키워드 구독

2026-11-09 구현: [키워드 구독 상세 설계](../design/keyword-subscriptions.md). 기존 부분 문자열 비교를 번역·분석 후 단어 특징 전체 포함 판정으로 대체했다. KEYWORD-01~03과 DB 등록 이벤트 생산자·분석·알림 워커를 연결했다. 습득물 등록 HTTP API는 별도 구현 영역이다.

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/me/keyword-subscriptions |
| 접근 | 인증된 본인(MEMBER 또는 ADMIN) |
| Request body | JSON |
| Request model | CreateKeywordSubscriptionRequest |
| 성공 | 201 KeywordSubscriptionResponse |
| 실패 | 공통 오류, 409 KEYWORD\_ALREADY\_SUBSCRIBED, 503 KEYWORD\_ANALYSIS\_UNAVAILABLE |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | string | 아니오 | ko 또는 en, 기본 ko |

### 처리 규칙

- keyword를 trim·Unicode NFKC 정규화·소문자화하여 중복 비교한다. trim한 원문은 화면 표시용으로 저장한다.
- 같은 회원에게 정규화된 키워드가 이미 있으면 409. 서로 다른 회원은 동일 키워드 구독 가능.
- 구독 입력과 신규 습득물의 공개 제목·설명을 같은 프로필로 번역·분석한다. 구독의 긍정 단어 특징이 물품의 특징에 모두 포함될 때 알린다. 순서·거리는 무관하며 명사구·WordNet 동의어 특징은 조건에서 제외한다. 사진 인식·비공개 정보·보관 위치는 검색 대상으로 쓰지 않는다.
- 분석 후 유효 단어 특징이 없으면 400 VALIDATION_ERROR(keyword 필드 NO_MATCHABLE_TERMS). 분석 서비스 일시 장애·busy·timeout·프로필 변경은 503 KEYWORD_ANALYSIS_UNAVAILABLE와 Retry-After: 5를 반환하고 구독은 저장하지 않는다. 분석 성공 후 저장하여 기존 응답 모델을 유지한다.
- 등록 당시 공개 텍스트로 판정한다. 등록 이후 생성된 구독과 처리 전에 해제된 구독은 제외한다. 상세 시점·복구 규칙은 설계 문서를 따른다.
- 기존 습득물에 대한 소급 알림은 만들지 않는다. 수정 이벤트만으로 키워드 알림을 새로 만들지 않는 것으로 제안한다.
- Location: /api/v1/me/keyword-subscriptions/\{subscriptionId\} 반환.

### Request body 예시

```json
{
  "keyword": "에어팟"
}
```

## KEYWORD-03 키워드 구독 해제

| 항목 | 내용 |
| --- | --- |
| Method / URL | DELETE /api/v1/me/keyword-subscriptions/\{subscriptionId\} |
| 접근 | 인증된 본인(MEMBER 또는 ADMIN) |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 204 No Content |
| 실패 | 공통 오류, 404 KEYWORD\_SUBSCRIPTION\_NOT\_FOUND |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Accept-Language | string | 아니오 | ko 또는 en, 기본 ko |
| path | subscriptionId | string(UUID) | 예 | 본인의 구독 ID |

### 처리 규칙

- 본인 구독만 삭제한다. 타인 또는 없는 구독은 404. 정상 응답 본문 없음.
- 해당 구독에서 아직 발송되지 않은 이메일을 제외한다. 이미 생성된 인앱 알림은 보존 정책을 따른다.
- 같은 물품이 다른 구독에도 일치하면 남아 있는 구독에 따른 알림은 계속 가능하다.

## Request model

### UpdateProfileRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| language | string(enum) | 예 | ko 또는 en. 변경 가능한 유일한 프로필 필드 |

### UpdateNotificationSettingsRequest

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| emailEnabled | boolean | 예 | 전체 이메일 수신 여부 |
| matchEmail | boolean | 예 | 신규 매칭 후보 이메일 |
| collectionEmail | boolean | 예 | 내 습득물 수거 완료 이메일 |
| expiryEmail | boolean | 예 | 내 습득물 만료 이메일 |
| keywordEmail | boolean | 예 | 구독 키워드 일치 이메일 |

인앱 알림은 끄지 않는다. digest 수신 여부는 별도 플래그로 만들지 않고 같은 종류별 수신 설정을 적용한다.

### UpdateNotificationRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| read | boolean | 예 | true만 허용. false 또는 null은 400 |

### CreateKeywordSubscriptionRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| keyword | string | 예 | trim 후 1\~50자. 공백만 불가. 길이 제한은 제안값 |

## Response model

### ProfileResponse

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| userId | string(UUID) | 예 | 본인 서비스 내부 ID |
| name | string | 예 | 목업 SSO의 가상 이름 |
| email | string(email) | 예 | 본인의 가상 이메일 |
| affiliation | string(enum) | 예 | STUDENT, FACULTY, STAFF |
| role | string(enum) | 예 | MEMBER, ADMIN. 현재 DB 권한 |
| language | string(enum) | 예 | ko, en |

```json
{
  "userId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
  "name": "테스트 학생 1",
  "email": "student01@example.com",
  "affiliation": "STUDENT",
  "role": "MEMBER",
  "language": "ko"
}
```

### NotificationSettingsResponse

UpdateNotificationSettingsRequest와 동일한 다섯 boolean을 항상 반환한다. 모두 필수이며 null은 없다.

```json
{
  "emailEnabled": true,
  "matchEmail": true,
  "collectionEmail": true,
  "expiryEmail": true,
  "keywordEmail": true
}
```

### NotificationResponse

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| notificationId | string(UUID) | 예 | 알림 ID |
| type | NotificationType | 예 | MATCH\_CANDIDATE, ITEM\_COLLECTED, ITEM\_EXPIRED, KEYWORD\_MATCH |
| message | string | 예 | 선택 언어의 일반 알림 문구. 민감 데이터·연락처 미포함 |
| targetPath | string | 예 | 허용된 관련 화면 상대 경로. 외부 URL·임의 리다이렉트 불가 |
| itemId | string(UUID) 또는 null | 예 | 연결된 습득물 ID |
| reportId | string(UUID) 또는 null | 예 | 매칭 알림의 분실 신고 ID. 다른 종류는 null |
| createdAt | string(date-time) | 예 | 알림 생성 시각 |
| readAt | string(date-time) 또는 null | 예 | 읽지 않았으면 null |

```json
{
  "notificationId": "95bf610c-868a-4336-8e7b-92a8b43f5013",
  "type": "MATCH_CANDIDATE",
  "message": "분실 신고와 일치할 수 있는 습득물이 등록되었습니다.",
  "targetPath": "/lost-reports/b40638c0-9382-4c4a-9af7-9319ba4887f1/matches",
  "itemId": "dab45e58-34af-4ba7-90cb-59471cc17a13",
  "reportId": "b40638c0-9382-4c4a-9af7-9319ba4887f1",
  "createdAt": "2026-11-02T15:00:01+09:00",
  "readAt": null
}
```

### KeywordSubscriptionResponse

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| subscriptionId | string(UUID) | 예 | 구독 ID |
| keyword | string | 예 | trim한 표시 키워드 |
| createdAt | string(date-time) | 예 | 구독 생성 시각 |

```json
{
  "subscriptionId": "29005fe7-8186-436c-a659-89093a8a3cbf",
  "keyword": "에어팟",
  "createdAt": "2026-11-02T15:10:00+09:00"
}
```

### NotificationPage / KeywordSubscriptionPage

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| items | NotificationResponse\[\] 또는 KeywordSubscriptionResponse\[\] | 예 | 해당 API의 목록 |
| page | integer | 예 | 현재 페이지 |
| size | integer | 예 | 요청한 페이지 크기 |
| totalElements | integer | 예 | 필터 적용된 전체 건수 |
| totalPages | integer | 예 | 전체 페이지 수. 비어 있으면0 |

```json
{
  "items": [],
  "page": 0,
  "size": 20,
  "totalElements": 0,
  "totalPages": 0
}
```

## 알림·이메일 내부 처리 계약

한도·digest 시각·재시도 간격은 [후속 이메일 설계](../design/notification-delivery.md)의 환경변수로 분리한다.
아래 20통·19통·20시·재시도 간격은 기본값 예시이며 고정 요구사항이 아니다.
한도·시각 변경은 다음 KST 날짜 정책부터 적용한다. 공개 API 모델은 변경하지 않는다.

2026-11-09 구현: 환경변수·가변 한도·digest·재시도는 mock 제공자로 연결했다. 실제 외부 메일은 보내지 않는다.
수거·만료 상태 변경의 outbox를 소비하며 해당 도메인 API나 만료 스케줄러 구현을 대체하지 않는다.

| 항목 | 규칙 |
| --- | --- |
| 신규 매칭 FR-17 | 각 신규 후보에 대해 신고 소유자의 인앱 알림 생성, 이메일 수신 허용 시 이메일 큐 등록 |
| 수거 FR-20 | 수거 완료 시 해당 습득물 작성자에게 인앱 알림. 이메일은 collectionEmail 설정 반영 |
| 만료 FR-25 | 30일 만료 시 작성자에게 인앱 알림. 이메일은 expiryEmail 설정 반영 |
| 키워드 FR-18 | 신규 습득물 등록 당시 공개 제목·설명의 분석 결과에 구독의 모든 단어 특징이 포함되면 구독자 알림 |
| 중복 방지 | 이벤트 ID·수신자·알림 종류로 유일성 보장. 하나의 물품이 여러 구독에 맞아도 키워드 알림은 한 번 |
| 후보와 키워드 | 같은 물품이 매칭·키워드에 각각 해당하면 서로 다른 종류 알림 가능. 종류 간 합치기는 추가 설계 선택 |
| 이메일 수신자 | 서버가 본인 계정 이메일에서 결정. API 요청으로 수신 이메일 지정 불가 |
| 이메일 내용 | 관련 페이지 링크와 일반 안내 문구만. 사진·보관 위치·비공개 식별 정보·상대 연락처를 넣지 않음 |
| 설정 재확인 | 실제 전송 직전 전체·종류별 수신 설정과 대상 상태를 다시 검사 |
| 해결 신고 | RESOLVED·CLOSED 신고의 추가 매칭 알림 중단. 대기 개별·요약 이메일에서도 제거 |
| 보안과 가용성 | 숨김·삭제 등으로 접근할 수 없는 항목은 알림의 상세 데이터를 노출하지 않음. 관련 페이지 권한 검사는 유지 |
| 실패 재시도 REL-2 | 영속 큐로 재시도. 외부 서비스 중단이 있어도 알림 유실 없이 대기·관리자 운영 확인. 무한 고속 재시도 금지 |
| 재시도 제안 | 1분·5분·30분 이후 점차 간격을 늘리고, 장기 실패는 운영 점검 큐에서 계속 재시도. 영구 주소 오류는 기록·점검 대상 |
| 중복 메일 | 논리적 메일 ID로 중복 방지. 전달 결과가 불명확하면 서비스의 idempotency 지원 범위에서 재시도 |
| 일일 한도 FR-19 | KST 하루0시\~24시, 회원별 최대20통 제안. 개별19통+저녁 요약1통을 예약하여 요약도 한도 안에 포함 |
| 저녁 요약 | 매일20:00 KST 제안. 개별 한도를 넘은 이벤트들을 한 통으로 묶음. 인앱은 전부 즉시 생성 |
| 요약 마감 이후 | 당일 개별 한도 소진 후20시 이후 발생한 알림은 다음 저녁 요약으로 이월. 제외·유실하지 않음 |
| 한도 경합 | 발송 슬롯을 원자적으로 예약. 한 메일 재시도는 같은 논리 슬롯으로 취급하며 새 알림으로 중복 집계하지 않음 |
| 수신 거부 | 요약에서도 해당 종류 제외. 전체 거부면 이메일을 보내지 않으며 인앱은 유지 |
| 환경 | 목업 계정의 알림 이메일은 테스트 수신함으로 라우팅. 실제 개인 메일 주소를 테스트 데이터로 수집하지 않음 |

숨김·종료 물품에 대한 알림 억제 범위와 요약의 마감 이후 이월은 세부 설계 제안이며 FR-16 후보 판정의 세 조건을 바꾸지 않는다.

## 개인정보·보존

- 프로필은 SRS3.3의 사용자 식별 정보·역할·언어만 사용한다. 설정·키워드·알림은 해당 명시 기능 구현에 필요한 운영 데이터로 제한한다.
- 이메일 설정이 꺼져도 보유 중인 이메일을 다른 회원에게 공개하지 않는다. 프런트엔드 로그·알림 로그에도 상대 연락처를 넣지 않는다.
- 알림 payload에는 분실 신고 비공개 식별 정보와 물품 메시지 원문을 저장하지 않는다. 종료 시 즉시 삭제해야 하는 데이터를 별도 알림 복제본으로 남기지 않는다.
- SRS는 알림·구독 자체의 보존기간을 명시하지 않았다. 알림 최대1년 또는 관련 레코드 영구 삭제 시 함께 삭제, 구독·설정은 계정 활성 기간 동안 유지하는 정책을 제안한다. 이를 확정 요구사항으로 간주하지 않는다.
- 신고가 종료되면 매칭 이메일의 대기 payload에서 해당 신고를 제거한다. 물품·신고 원문을 이메일 큐에 복제하지 않고 ID로 참조한다.
- 언어 설정은 UI 전환과 함께 갱신하며 프런트엔드 모든 화면의 한영 지원은 별도 UI 검증이 필요하다.

## 오류·검증 기준

추가 오류: 404 NOTIFICATION\_NOT\_FOUND, 404 KEYWORD\_SUBSCRIPTION\_NOT\_FOUND, 409 KEYWORD\_ALREADY\_SUBSCRIBED. 타인 리소스는 없는 리소스와 동일하게 404다.

```json
{
  "code": "VALIDATION_ERROR",
  "message": "입력값을 확인해주세요.",
  "fieldErrors": [
    {
      "field": "language",
      "code": "INVALID_FORMAT",
      "message": "ko 또는 en을 선택해주세요."
    }
  ]
}
```

| 확인 상황 | 기대 결과 |
| --- | --- |
| 모든 개인 API에 비회원 접근 | 401 |
| 프로필 PATCH로 role·email 전달 | 400, 권한·신원 정보 변경 없음 |
| language=en 변경 후 auth/me 조회 | en 일치 |
| 이메일 전체 off + 신규 후보 | 인앱 생성, 이메일 없음 |
| matchEmail=false만 설정 | 매칭 이메일만 제외, 다른 종류 설정 유지 |
| 해결 직전 큐에 있던 매칭 이메일 | 실제 발송 전 종료 상태 확인 후 제외 |
| 이메일 실패·작업 재실행 | 재시도되며 인앱·후보 중복 없음 |
| 하루에 다수 이벤트 발생 | 모든 인앱 알림 유지, 개별 한도+저녁 요약 적용 |
| 요약 큐의 민감 물품 | 링크·일반 안내만 포함. 사진·보관 위치 없음 |
| 동일 키워드 공백·대소문자 차이 | 정규화 후 중복이면409 |
| 다른 회원의 알림 읽음·구독 삭제 | 404, 변경 없음 |
| 새 습득물이 여러 구독과 일치 | 키워드 알림은 회원·물품별 한 번 |

## 명시적 제안값

미활동 세션 정책은 인증 문서를 따른다. 이메일 한도20통·개별19통·20시 요약, 키워드1\~50자, 알림 보존기간, 읽음 API는 설계 제안이다. 기존 substring 비교 제안은 2026-11-09 단어 특징 전체 포함 설계로 대체했다. FR-17 필수 이메일은 회원이 수신 거부하지 않는 한 유지하며, FR-19 요약 기능을 제외하는 경우에도 FR-17 자체를 제거하지 않는다.

