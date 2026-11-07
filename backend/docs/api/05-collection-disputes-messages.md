# 수거·분쟁·메시지

> 원문: [Notion](https://app.notion.com/p/40c23542cf8c8109afd2de2f369294d2?pvs=204) · 내보낸 날짜: 2026-11-02 (KST)

## 범위와 우선순위

수거 완료·취소, 수거 분쟁, 물품별 메시지 API를 정의한다.

| 우선순위 | SRS | 기능 |
| --- | --- | --- |
| Must | FR-20, FR-22 | 수거 완료, 관련 분실 신고 종료 |
| Should | FR-21, FR-23, FR-24 | 수거 취소, 분쟁, 메시지 |

경로·필드 길이·페이지 크기 등 SRS에 없는 값은 설계 제안이다.

## 공통 요청·응답 규칙

인증·공통 오류는 [인증](01-auth.md) 문서를 따른다.

### 인증과 요청

| 항목 | 규칙 |
| --- | --- |
| Base URL | <code>/api/v1</code> |
| 통신 | HTTPS |
| 인증 쿠키 | <code>KAIFIND_SESSION</code> — HttpOnly·Secure·SameSite=Lax |
| 인증 헤더 | Authorization Bearer 사용 안 함 |
| 쓰기 요청 | <code>X-CSRF-Token</code> 필수, 허용 Origin 검사 |
| JSON 본문 | <code>Content-Type: application/json</code> |
| 권한 검사 | 모든 요청에서 서버가 인증·인가 확인. ADMIN은 MEMBER 기능도 사용 가능 |
| 입력 검증 | 미정의 필드·null·잘못된 타입 거부. 명세에 없는 추가 요청 필드 없음 |

### 데이터 형식과 응답

| 항목 | 규칙 |
| --- | --- |
| ID | UUID 문자열 |
| 시각 | RFC 3339, KST 오프셋 <code>+09:00</code> |
| 날짜 | <code>YYYY-MM-DD</code> |
| 캐시 | 모든 응답에 <code>Cache-Control: no-store</code> |
| 언어 선택 | <code>Accept-Language: ko</code> 또는 <code>en</code>. 기본값 ko |
| 언어 응답 | 선택 언어로 message·fieldErrors\[\].message 반환, Content-Language 표시 |
| 성공 응답 | 응답 모델 직접 반환. HTTP 204에는 본문 없음 |

### 페이지네이션

목록은 <code>Page[T]</code> 형식이다. T는 해당 목록의 응답 모델이다. 각 API의 정렬 기준을 적용하고 시각이 같으면 UUID로 정렬한다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| items | T 배열 | 현재 페이지 결과 |
| page | integer | 기본 0, 최솟값 0 |
| size | integer | 기본 20, 허용 범위 1\~100 |
| totalElements | integer | 전체 결과 수 |
| totalPages | integer | 전체 페이지 수 |

### 공통 오류

| HTTP | 오류 코드 |
| --- | --- |
| 400 | <code>VALIDATION_ERROR</code>, <code>MALFORMED_JSON</code> |
| 401 | <code>AUTH_REQUIRED</code>, <code>SESSION_EXPIRED</code> |
| 403 | <code>CSRF_INVALID</code>, <code>ORIGIN_NOT_ALLOWED</code>, <code>FORBIDDEN</code> |
| 404 | <code>NOT_FOUND</code> |
| 415 | <code>UNSUPPORTED_MEDIA_TYPE</code> |
| 500 | <code>INTERNAL_SERVER_ERROR</code> |

존재하지 않는 리소스와 비참여자에게 숨겨야 하는 대화는 404를 반환한다. 존재를 알 수 있는 수거·분쟁 작업에서 권한이 부족하면 403을 반환한다.

**ErrorResponse**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| code | string | 오류 식별 코드 |
| message | string | 선택 언어의 오류 메시지 |
| fieldErrors | FieldError 배열 | 필드별 오류 목록 |

**FieldError**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| field | string | 오류가 발생한 필드 |
| code | string | 필드 오류 식별 코드 |
| message | string | 선택 언어의 필드 오류 메시지 |

## 엔드포인트 목록

아래 경로에서 Base URL <code>/api/v1</code>을 생략했다. 요청·응답 모델과 세부 권한은 각 API의 상세 표에서 확인한다.

### 수거

| ID | Method | Endpoint | 기능 |
| --- | --- | --- | --- |
| COL-01 | POST | <code>/found-items/{itemId}/collection</code> | 수거 완료 |
| COL-02 | GET | <code>/found-items/{itemId}/collection</code> | 현재 수거 기록 |
| COL-03 | DELETE | <code>/found-items/{itemId}/collection</code> | 잘못된 수거 취소 |

| ID | 권한 | Request model | 성공 응답 |
| --- | --- | --- | --- |
| COL-01 | 회원, 수거권한 제한 없음 | CollectRequest | 201 CollectionResponse |
| COL-02 | 작성자·수거자·관리자 | 없음 | 200 CollectionResponse |
| COL-03 | 작성자·수거자·관리자 | 없음 | 204 |

### 분쟁

| ID | Method | Endpoint | 기능 |
| --- | --- | --- | --- |
| DSP-01 | POST | <code>/found-items/{itemId}/disputes</code> | 수거 이의 제기 |
| DSP-02 | GET | <code>/found-items/{itemId}/disputes</code> | 내 게시물 분쟁 목록 |

| ID | 권한 | Request model | 성공 응답 |
| --- | --- | --- | --- |
| DSP-01 | 게시물 작성자 | CreateDisputeRequest | 201 DisputeResponse |
| DSP-02 | 게시물 작성자·관리자 | 없음 | 200 Page\[DisputeResponse\] |

### 메시지

| ID | Method | Endpoint | 기능 |
| --- | --- | --- | --- |
| MSG-01 | POST | <code>/conversations</code> | 물품별 대화 시작·재사용 |
| MSG-02 | GET | <code>/conversations</code> | 내 대화 목록 |
| MSG-03 | GET | <code>/conversations/{conversationId}/messages</code> | 메시지 조회 |
| MSG-04 | POST | <code>/conversations/{conversationId}/messages</code> | 메시지 전송 |

| ID | 권한 | Request model | 성공 응답 |
| --- | --- | --- | --- |
| MSG-01 | 작성자 외 회원 | CreateConversationRequest | 201 또는 200 ConversationResponse |
| MSG-02 | 대화 참여자 | 없음 | 200 Page\[ConversationResponse\] |
| MSG-03 | 해당 대화 참여자 | 없음 | 200 Page\[MessageResponse\] |
| MSG-04 | 해당 대화 참여자 | SendMessageRequest | 201 MessageResponse |

## COL-01 수거 완료

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/found-items/\{itemId\}/collection |
| 접근 | 회원, 수거권한 제한 없음 |
| Request body | JSON |
| Request model | CollectRequest |
| 성공 | 201 CollectionResponse |
| 추가 실패 | 403 COLLECTION\_RESTRICTED, 409 ITEM\_NOT\_POSTED / ALREADY\_COLLECTED |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | ko 또는 en | 아니오 | 오류 표시 언어, 기본 ko |
| path | itemId | UUID | 예 | 대상 습득물 ID |

### Request model: CollectRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| confirmedOwnership | boolean | 예 | 반드시 true. 수거 후 본인의 물건임을 확인 |

```json
{
  "confirmedOwnership": true
}
```

### 처리 규칙

1. 학교 신원에 의한 실제 소유권 확인·작성자 승인은 요구하지 않는다. 사용자의 확인만 받는다.
2. 수거권한 제한 상태와 게시물 상태 POSTED를 확인한다. 제한은 회원 전체 권한이 아니라 수거 표시 권한만 차단한다. 숨김 게시물에 대한 새 수거 표시는 404 NOT\_FOUND로 거부한다.
3. 트랜잭션·조건부 갱신과 유일성 제약으로 활성 수거자는 물품당 한 명만 허용한다. 동시 요청 중 한 건만 성공하고 나머지는 409.
4. 수거자 ID와 수거 시각을 서버가 기록하고 물품을 COLLECTED로 변경한다. 감사 로그를 기록한다.
5. 해당 수거자의 분실 신고 중 이 물품이 매칭 후보로 연결된 신고를 모두 종료 상태로 만든다. OPEN 신고는 RESOLVED로 전환하고 이미 RESOLVED 또는 CLOSED이면 종료 상태를 유지한다. 타인의 신고는 종료하지 않는다. 종료한 신고의 private identifying details를 즉시 삭제하고 추가 매칭 알림을 중단한다.
6. 물품 종료와 함께 모든 관련 대화·메시지·미리보기·서버 캐시를 삭제한다. 메시지 본문은 감사 로그에 남기지 않는다.
7. 작성자 알림을 신뢰성 있게 예약한다. 이메일은 수신 설정을 반영하며 실패 시 재시도한다. 상태 변경·연동 종료·삭제·감사·알림 예약은 하나의 원자적 처리 또는 동등한 일관성 보장으로 수행한다.

### Response

```json
{
  "collectionId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
  "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
  "collectorId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
  "collectedAt": "2026-11-02T16:00:00+09:00",
  "status": "COLLECTED"
}
```

응답의 전체 필드 정의는 아래 공통 모델을 따른다.

## COL-02 현재 수거 기록

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/found-items/\{itemId\}/collection |
| 접근 | 작성자·수거자·관리자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 CollectionResponse |
| 추가 실패 | 403 FORBIDDEN, 404 COLLECTION\_NOT\_FOUND |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | Accept-Language | ko 또는 en | 아니오 | 오류 표시 언어, 기본 ko |
| path | itemId | UUID | 예 | 대상 습득물 ID |

### Request model: 없음

본문을 보내지 않는다. Path·Query 외 추가 파라미터 없음.

### 처리 규칙

1. 현재 유효한 수거 기록만 반환한다. 작성자·현재 수거자·관리자만 조회 가능하다.
2. 수거자의 이메일·전화번호·분실 신고 상세를 반환하지 않는다.

### Response

```json
{
  "collectionId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
  "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
  "collectorId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
  "collectedAt": "2026-11-02T16:00:00+09:00",
  "status": "COLLECTED"
}
```

응답의 전체 필드 정의는 아래 공통 모델을 따른다.

## COL-03 잘못된 수거 취소

| 항목 | 내용 |
| --- | --- |
| Method / URL | DELETE /api/v1/found-items/\{itemId\}/collection |
| 접근 | 작성자·수거자·관리자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 204 |
| 추가 실패 | 403 FORBIDDEN, 409 ITEM\_NOT\_COLLECTED |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Accept-Language | ko 또는 en | 아니오 | 오류 표시 언어, 기본 ko |
| path | itemId | UUID | 예 | 대상 습득물 ID |

### Request model: 없음

본문을 보내지 않는다. Path·Query 외 추가 파라미터 없음.

### 처리 규칙

1. 현재 수거자, 게시물 작성자 또는 관리자만 취소한다. 로그인만 한 제3자는 거부한다. 숨김 여부와 무관하게 이 관계자들의 잘못된 수거 취소는 허용하는 설계 제안으로 권리를 유지한다.
2. 현재 상태가 COLLECTED일 때 활성 수거 표시를 해제하고 POSTED로 돌린다. 수거자·시각 및 취소 행위자는 보존 규칙에 따라 감사 기록에 남긴다.
3. 트랜잭션으로 상태·수거기록 갱신·감사 로그를 함께 처리한다. 이미 취소되었으면 409.
4. 이미 삭제된 메시지·비공개 식별 정보를 복원하지 않는다. 자동 종료된 분실 신고를 자동 재개하지 않는 것은 설계 제안이며 SRS에 명시된 동작이 아니다.
5. 다시 POSTED가 된 시점의 만료 계산은 습득물 명세의 재게시 기준을 따른다.

### Response

응답의 전체 필드 정의는 아래 공통 모델을 따른다.

## DSP-01 수거 이의 제기

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/found-items/\{itemId\}/disputes |
| 접근 | 게시물 작성자 |
| Request body | JSON |
| Request model | CreateDisputeRequest |
| 성공 | 201 DisputeResponse |
| 추가 실패 | 403 FINDER\_ONLY, 409 ITEM\_NOT\_COLLECTED / OPEN\_DISPUTE\_EXISTS |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | ko 또는 en | 아니오 | 오류 표시 언어, 기본 ko |
| path | itemId | UUID | 예 | 대상 습득물 ID |

### Request model: CreateDisputeRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| reason | string | 예 | 공백 제외1\~1000자, 추가 개인정보 입력 유도 금지 |

```json
{
  "reason": "수거 표시가 잘못된 것 같습니다."
}
```

### 처리 규칙

1. 게시물 작성자만 현재 COLLECTED 상태의 수거 표시에 이의를 제기할 수 있다. 게시물이 숨겨졌어도 작성자의 이의 제기는 허용하는 설계 제안이다.
2. 현재 collectionId와 연결한다. 취소 후 다시 수거되면 새 수거 기록으로 구분한다.
3. 동일 수거 기록에 OPEN 분쟁은 1건만 허용하는 것은 중복 방지를 위한 제안이다.
4. 분쟁 제출 자체는 물품 상태를 바꾸거나 수거자를 차단하지 않는다. 관리자 검토가 필요하다.
5. 수거 시 삭제된 메시지는 분쟁을 위해 보존·복원하지 않는다. 검토는 수거 기록·감사 로그를 사용한다.

### Response

```json
{
  "disputeId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd",
  "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
  "collectionId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
  "reason": "수거 표시가 잘못된 것 같습니다.",
  "status": "OPEN",
  "createdAt": "2026-11-02T16:05:00+09:00",
  "decision": null,
  "resolvedAt": null
}
```

응답의 전체 필드 정의는 아래 공통 모델을 따른다.

## DSP-02 내 게시물 분쟁 목록

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/found-items/\{itemId\}/disputes |
| 접근 | 게시물 작성자·관리자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 Page\[DisputeResponse\] |
| 추가 실패 | 403 FORBIDDEN |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | Accept-Language | ko 또는 en | 아니오 | 오류 표시 언어, 기본 ko |
| path | itemId | UUID | 예 | 대상 습득물 ID |
| query | page | integer | 아니오 | 기본0, 최소0 |
| query | size | integer | 아니오 | 기본20, 1\~100 |

### Request model: 없음

본문을 보내지 않는다. Path·Query 외 추가 파라미터 없음.

### 처리 규칙

1. 해당 게시물 작성자 또는 관리자만 조회한다.
2. createdAt 내림차순. 분쟁 메타데이터만 제공하며 삭제된 메시지·연락처는 포함하지 않는다.

### Response

```json
{
  "items": [
    {
      "disputeId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd",
      "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
      "collectionId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
      "reason": "수거 표시가 잘못된 것 같습니다.",
      "status": "OPEN",
      "createdAt": "2026-11-02T16:05:00+09:00",
      "decision": null,
      "resolvedAt": null
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

응답의 전체 필드 정의는 아래 공통 모델을 따른다.

## MSG-01 물품별 대화 시작·재사용

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/conversations |
| 접근 | 작성자 외 회원 |
| Request body | JSON |
| Request model | CreateConversationRequest |
| 성공 | 201 또는 200 ConversationResponse |
| 추가 실패 | 409 ITEM\_CLOSED / SELF\_CONVERSATION |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | ko 또는 en | 아니오 | 오류 표시 언어, 기본 ko |

### Request model: CreateConversationRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| itemId | UUID | 예 | 연락할 습득물 ID |

```json
{
  "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020"
}
```

### 처리 규칙

1. 회원이 특정 물품의 작성자에게 문의하는 대화를 생성한다. memberId·finderId는 서버가 인증 사용자와 게시물에서 결정한다. 숨김 게시물의 새 대화 생성은 404 NOT\_FOUND로 거부한다.
2. 작성자 본인과의 자기 대화는 생성하지 않는다. 작성자는 회원이 시작한 기존 대화에서 응답한다.
3. 같은 물품에 대해 같은 참여자 조합(물품 작성자·문의회원)의 채팅방은 중복 생성할 수 없다. POSTED 물품의 (itemId, 문의회원ID) 조합에 대화는 최대 1개이며, 처음이면 201, 이미 있으면 동일 대화를 200으로 반환한다. 동시 생성 요청에도 DB의 UNIQUE(item_id, member_id) 제약으로 중복을 방지하고 동일 대화를 반환한다.
4. COLLECTED/EXPIRED 물품의 대화는 종료 시 삭제되므로 새 대화도 생성하지 않는다.
5. 직접 보관(kept by me) 물품도 이 API로 연락한다. 이메일·전화번호를 전달하지 않는다.
6. 숨김 전 생성된 대화는 기존 참여자의 조회·전송을 허용한다. 숨김 상태에서는 기존 대화가 있어도 이 생성 API는 404를 반환한다. 대화 재사용만으로 updatedAt을 변경하지 않는다.

### Response

```json
{
  "conversationId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
  "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
  "finderId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
  "memberId": "d45aee05-299e-4da9-aea5-dfdac5bd405a",
  "createdAt": "2026-11-02T15:00:00+09:00",
  "updatedAt": "2026-11-02T15:05:00+09:00"
}
```

응답의 전체 필드 정의는 아래 공통 모델을 따른다.

## MSG-02 내 대화 목록

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/conversations |
| 접근 | 대화 참여자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 Page\[ConversationResponse\] |
| 추가 실패 | 없음 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | Accept-Language | ko 또는 en | 아니오 | 오류 표시 언어, 기본 ko |
| query | page | integer | 아니오 | 기본0, 최소0 |
| query | size | integer | 아니오 | 기본20, 1\~100 |
| query | itemId | UUID | 아니오 | 특정 물품 대화만 필터 |

### Request model: 없음

본문을 보내지 않는다. Path·Query 외 추가 파라미터 없음.

### 처리 규칙

1. 현재 사용자가 finderId 또는 memberId인 대화만 반환한다. 요청에서 타 사용자 ID를 받지 않는다.
2. updatedAt 내림차순. 종료된 물품의 삭제 대화는 포함하지 않는다.
3. 대화 요약에 메시지 본문 미리보기와 상대 연락처를 포함하지 않는다.

### Response

```json
{
  "items": [
    {
      "conversationId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
      "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
      "finderId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
      "memberId": "d45aee05-299e-4da9-aea5-dfdac5bd405a",
      "createdAt": "2026-11-02T15:00:00+09:00",
      "updatedAt": "2026-11-02T15:05:00+09:00"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

응답의 전체 필드 정의는 아래 공통 모델을 따른다.

## MSG-03 메시지 조회

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/conversations/\{conversationId\}/messages |
| 접근 | 해당 대화 참여자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 Page\[MessageResponse\] |
| 추가 실패 | 404 CONVERSATION\_NOT\_FOUND |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | Accept-Language | ko 또는 en | 아니오 | 오류 표시 언어, 기본 ko |
| path | conversationId | UUID | 예 | 대화 ID |
| query | page | integer | 아니오 | 기본0, 최소0 |
| query | size | integer | 아니오 | 기본20, 1\~100 |

### Request model: 없음

본문을 보내지 않는다. Path·Query 외 추가 파라미터 없음.

### 처리 규칙

1. 대화 참여자 두 명만 메시지를 조회한다. 관리자라는 이유만으로 메시지 접근을 허용하지 않는다.
2. createdAt 오름차순. 서버가 종료된 물품의 메시지 삭제를 확인한다.
3. 닫혀 삭제된 대화 또는 비참여자의 대화는 404로 반환한다.

### Response

```json
{
  "items": [
    {
      "messageId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd",
      "conversationId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
      "senderId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
      "content": "보관 위치에서 물품을 찾지 못했습니다.",
      "createdAt": "2026-11-02T15:05:00+09:00"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

응답의 전체 필드 정의는 아래 공통 모델을 따른다.

## MSG-04 메시지 전송

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/conversations/\{conversationId\}/messages |
| 접근 | 해당 대화 참여자 |
| Request body | JSON |
| Request model | SendMessageRequest |
| 성공 | 201 MessageResponse |
| 추가 실패 | 404 CONVERSATION\_NOT\_FOUND, 409 ITEM\_CLOSED |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | ko 또는 en | 아니오 | 오류 표시 언어, 기본 ko |
| path | conversationId | UUID | 예 | 대화 ID |

### Request model: SendMessageRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| content | string | 예 | 앞뒤 공백 제거 후 1\~2000자. 내부 공백·줄바꿈 보존. 일반 텍스트로만 렌더링하며 HTML 실행 금지 |

```json
{
  "content": "보관 위치에서 물품을 찾지 못했습니다."
}
```

### 처리 규칙

1. 현재 사용자가 해당 물품 작성자 또는 이 대화의 문의회원인지 확인한다.
2. senderId·작성시각은 서버가 결정한다. 연락처 전용 필드는 없으며, 메시지 본문에 포함된 이메일·전화번호를 검사하거나 차단하지 않는다.
3. 물품 POSTED 여부와 저장을 원자적으로 검사한다. 동시에 수거·만료가 발생하면 종료 후 메시지가 남지 않게 한다.
4. 생성한 메시지는 참여자에게만 반환한다. 요청·오류·감사 로그에 본문을 기록하지 않는다.
5. 실시간 웹소켓은 SRS 필수가 아니다. 기본은 목록 API 재조회 방식이다.
6. 메시지 저장과 대화 updatedAt 갱신은 같은 트랜잭션에서 처리한다. 종료 처리와 경합하여 대화가 이미 삭제되었으면 404 CONVERSATION_NOT_FOUND를 반환한다. 재전송 요청의 중복 메시지 방지는 현재 지원하지 않는다.

### Response

```json
{
  "messageId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd",
  "conversationId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
  "senderId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
  "content": "보관 위치에서 물품을 찾지 못했습니다.",
  "createdAt": "2026-11-02T15:05:00+09:00"
}
```

응답의 전체 필드 정의는 아래 공통 모델을 따른다.

## 공통 Response Model

| 모델 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| CollectionResponse | collectionId | UUID | 예 | 수거 기록 ID |
| CollectionResponse | itemId | UUID | 예 | 물품 ID |
| CollectionResponse | collectorId | UUID | 예 | 내부 수거자 ID. 연락처 아님 |
| CollectionResponse | collectedAt | date-time | 예 | 수거 표시 시각 |
| CollectionResponse | status | COLLECTED | 예 | 현재 상태 |
| DisputeResponse | disputeId / itemId / collectionId | UUID 각각 | 예 | 분쟁·물품·대상 수거 기록 ID |
| DisputeResponse | reason | string | 예 | 분쟁 사유 |
| DisputeResponse | status | OPEN 또는 RESOLVED | 예 | 처리 상태 |
| DisputeResponse | createdAt | date-time | 예 | 제기 시각 |
| DisputeResponse | decision | UPHELD 또는 DISMISSED 또는 null | 예 | 인용·기각, 미처리 null |
| DisputeResponse | resolvedAt | date-time 또는 null | 예 | 검토 완료 시각 |
| ConversationResponse | conversationId / itemId / finderId / memberId | UUID 각각 | 예 | 대화·물품·참여자 ID. 이름·이메일·전화번호 없음 |
| ConversationResponse | createdAt / updatedAt | date-time 각각 | 예 | 생성·마지막 메시지 시각 |
| MessageResponse | messageId / conversationId / senderId | UUID 각각 | 예 | 메시지·대화·발신자 ID |
| MessageResponse | content | string | 예 | 일반 텍스트 |
| MessageResponse | createdAt | date-time | 예 | 서버 생성시각 |

## 보존·SRS 검증

| 요구사항 | 반영·검증 기준 |
| --- | --- |
| FR-20 | 수거 확인 true만 허용, POSTED만 수거, 동시 2명 중 1명 성공, 작성자 알림 |
| FR-21 | 수거자·작성자·관리자만 취소. POSTED 복귀 |
| FR-22 | 수거자 본인의 연결 후보 신고 전부 종료·타인 신고 유지 |
| FR-23 | 작성자만 이의 제기, 관리자가 검토·수거 권한만 제한 |
| FR-24 / SEC-3 | 특정 물품의 작성자와 회원 간 1:1 메시지, 연락처 비공개 |
| SEC-5 / 3.3 | COLLECTED·EXPIRED 즉시 메시지 삭제. 로그·캐시·목록에 잔존 금지 |
| FR-30 | 수거·취소 상태 변경의 행위자·대상·시각 감사 기록. 메시지 본문 미기록 |
| 3.3 보존 | 수거 표시·감사 로그 1년. 분쟁은 수거 기록의 검토 메타데이터로서 동일 보존기간을 적용하는 설계 제안 |

분쟁 기간 메시지 추가 보존은 SRS 5.2의 미정 사항이므로 이 초안은 현행 SEC-5의 즉시 삭제를 따른다. 분쟁 중복 정책·수거 취소 후 신고 재개·대화 최대 길이는 설계 제안이며 SRS 확정 정책으로 간주하지 않는다.


## 분쟁 구현 정책 (2026-11-07)

DSP-01·DSP-02는 세션 인증·CSRF 검증을 적용한다. 사유는 앞뒤 공백 제거 후
1~1000자로 검증한다. 숨김 게시물은 작성자가 접수·조회할 수 있고, 삭제되거나
존재하지 않는 게시물은 두 API 모두 404 NOT_FOUND다. 관리자도 작성자가 아니라면
접수할 수 없으며 목록 조회만 허용한다.

접수는 물품 → 현재 활성 수거 기록 순서로 잠그고 현재 COLLECTED 상태를 검사한다.
현재 수거 기록이 없는 경우에도 409 ITEM_NOT_COLLECTED다. 수거 생성·취소 구현은
동일한 물품 잠금을 먼저 획득해야 한다. 중복 OPEN 분쟁은 부분 유일 인덱스로도 방어하고
409 OPEN_DISPUTE_EXISTS로 반환한다. 접수 자체는 수거 상태·권한을 변경하지 않는다.

취소된 수거의 분쟁도 유지하며 재수거는 새 collectionId로 구분한다. 처리 완료 후
같은 수거에 새 분쟁을 접수할 수 있다. 목록은 과거 수거 기록을 포함하여
createdAt DESC, disputeId DESC로 정렬한다. 분쟁 purge_after는 연결된 수거의
purge_after를 그대로 사용하여 재접수로 수거 기록의 보존기간을 연장하지 않는다.
물품 삭제 후 남은 분쟁은 기존 관리자 API로 조회·검토할 수 있다.
