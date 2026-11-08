# 분실 신고·매칭

> 원문: [Notion](https://app.notion.com/p/40c23542cf8c819a997be29cf7bea67d?pvs=204) · 내보낸 날짜: 2026-11-02 (KST)

## 범위와 공통 계약

이 문서는 SRS 기반 API 설계 초안이다. 경로·DTO·문자수 제한·키워드 비교 방식·처리 시각은 설계 제안이다. SRS의 30일 종료, 1년 보존, 권한·삭제 요구사항은 유지한다. 인증·공통 오류 형식은 [인증](01-auth.md)을 따른다.

### 요청·응답 형식

| 항목 | 규칙 |
| --- | --- |
| Base URL | /api/v1 |
| 언어 | 선택 헤더 Accept-Language: ko 또는 en, 미지원·미입력 시 ko. Content-Language 반환 |
| 데이터 형식 | UUID 식별자, RFC3339 KST +09:00 시각, YYYY-MM-DD 날짜 |
| 캐시 | 개인 데이터는 Cache-Control: no-store |

### 인증·권한·적용 범위

| 항목 | 규칙 |
| --- | --- |
| 인증 | 모든 엔드포인트 MEMBER 또는 ADMIN의 KAIFIND\_SESSION 쿠키 필요 |
| 쓰기 요청 | X-CSRF-Token 필수. JSON 본문이 있으면 Content-Type: application/json 필수 |
| 읽기 요청 | Request body 없음. Content-Type·CSRF 불필요 |
| 검증 | 알 수 없는 JSON 필드, null, 잘못된 타입 거부. 빈 문자열은 trim 후 판정 |

### 목록·페이지네이션

| 항목 | 규칙 |
| --- | --- |
| 페이지네이션 | page 기본0, size 기본20·최대100, page>=0, 1\<=size\<=100 |

### 개인정보·접근 제어

| 항목 | 규칙 |
| --- | --- |
| 연락처 | 타인의 이메일·전화번호를 응답에 포함하지 않음 |

### 오류 처리

| 항목 | 규칙 |
| --- | --- |
| HTTP 400 | <code>MALFORMED_JSON / VALIDATION_ERROR</code> |
| HTTP 401 | <code>AUTH_REQUIRED / SESSION_EXPIRED</code> |
| HTTP 403 | <code>CSRF_INVALID / ORIGIN_NOT_ALLOWED</code> |
| HTTP 415 | <code>UNSUPPORTED_MEDIA_TYPE</code> |
| HTTP 500 | <code>INTERNAL_SERVER_ERROR</code> |
| ErrorResponse | code: string; message: string; fieldErrors: FieldError 배열 |
| FieldError | field: string; code: string; message: string. 필드 오류가 없으면 빈 배열 |

아래 각 Parameter 표에는 공통 인증·CSRF도 명시한다. GET에서 path/query가 없는 경우 별도 입력은 없다. 각 요청 모델·응답 모델은 문서 후반에 필드별로 정의한다.

## 요구사항과 엔드포인트

### 분실 신고

| ID | Method | Endpoint |
| --- | --- | --- |
| LOST-01 | POST | <code>/lost-reports</code> |
| LOST-02 | GET | <code>/lost-reports</code> |
| LOST-03 | GET | <code>/lost-reports/{reportId}</code> |
| LOST-04 | PUT | <code>/lost-reports/{reportId}</code> |
| LOST-05 | POST | <code>/lost-reports/{reportId}/extend</code> |
| LOST-06 | POST | <code>/lost-reports/{reportId}/resolve</code> |

| ID | Request model | 성공 | SRS |
| --- | --- | --- | --- |
| LOST-01 | CreateLostReportRequest | 201 LostReportResponse | FR-10,16,17 |
| LOST-02 | 없음 | 200 LostReportPage | 마이페이지 |
| LOST-03 | 없음 | 200 LostReportResponse | FR-10 |
| LOST-04 | UpdateLostReportRequest | 200 LostReportResponse | FR-16 |
| LOST-05 | 없음 | 200 LostReportResponse | FR-11 |
| LOST-06 | 없음 | 200 LostReportResponse | FR-12,22 |

### 매칭 후보

| ID | Method | Endpoint |
| --- | --- | --- |
| MATCH-01 | GET | <code>/lost-reports/{reportId}/matches</code> |

| ID | Request model | 성공 | SRS |
| --- | --- | --- | --- |
| MATCH-01 | 없음 | 200 MatchCandidatePage | FR-16,17 |

## LOST-01 분실 신고 등록

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/lost-reports |
| 접근 | MEMBER 또는 ADMIN. 별도 소유권 규칙은 아래 참조 |
| Request body | JSON |
| Request model | CreateLostReportRequest |
| 성공 | 201 LostReportResponse |
| 실패 | 공통 실패, 400 INVALID\_REFERENCE |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 인증된 현재 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | string | 아니오 | ko 또는 en. 기본 ko |

### 처리 규칙

- 현재 로그인 사용자를 ownerId로 지정한다. ownerId·status·만료 시각을 요청받지 않는다.
- 활성 카테고리, 중복 없는 활성 건물 1개 이상, 분실 날짜 범위, 비공개 식별 정보를 검증한다.
- OPEN으로 저장하고 expiresAt=createdAt+30일로 설정한다. Location: /api/v1/lost-reports/\{reportId\} 반환.
- 생성 커밋과 연결된 내부 작업으로 매칭을 수행한다. 신규 후보는 신고자 마이페이지·이메일 알림 대상이며 알림 수신 설정을 반영한다.
- 비공개 식별 정보는 본인·관리자 외 응답과 검색·알림·매칭 키워드에 사용하지 않는다.

### 요청 예시

```json
{
  "categoryId": "20e550a3-0cbb-419c-99a9-585aa9dadc58",
  "description": "검은색 이어폰 케이스",
  "possibleBuildingIds": [
    "846fe322-488c-424a-977c-bde931ed53de"
  ],
  "lostDateFrom": "2026-11-01",
  "lostDateTo": "2026-11-02",
  "privateIdentifyingDetails": "케이스 안쪽 별 모양 스티커"
}
```

## LOST-02 내 분실 신고 목록

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/lost-reports |
| 접근 | MEMBER 또는 ADMIN. 별도 소유권 규칙은 아래 참조 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 LostReportPage |
| 실패 | 공통 실패 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 인증된 현재 세션 |
| header | Accept-Language | string | 아니오 | ko 또는 en. 기본 ko |
| query | page | integer | 아니오 | 기본0, 0 이상 |
| query | size | integer | 아니오 | 기본20, 1\~100 |
| query | status | LostReportStatus | 아니오 | OPEN, RESOLVED, CLOSED. 생략 시 전체 |

### 처리 규칙

- 항상 현재 사용자의 신고만 반환한다. 관리자도 이 엔드포인트에서는 자신의 신고만 조회한다.
- createdAt 내림차순, 동률 reportId 내림차순. 다른 사용자 ID 필터는 받지 않는다.
- 비공개 정보는 목록에 포함하지 않는다. 상세에서 본인·관리자 권한 확인 후 조회한다.

## LOST-03 분실 신고 상세

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/lost-reports/\{reportId\} |
| 접근 | MEMBER 또는 ADMIN. 별도 소유권 규칙은 아래 참조 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 LostReportResponse |
| 실패 | 공통 실패, 404 LOST\_REPORT\_NOT\_FOUND |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 인증된 현재 세션 |
| header | Accept-Language | string | 아니오 | ko 또는 en. 기본 ko |
| path | reportId | string(UUID) | 예 | 대상 분실 신고 ID |

### 처리 규칙

- 신고자 본인 또는 관리자만 조회할 수 있다. 타 회원에게는 존재 여부를 숨기는 404를 반환한다.
- 종료된 신고의 privateIdentifyingDetails는 이미 삭제되어 null이다. 관리자도 복원·조회할 수 없다.

## LOST-04 분실 신고 수정

| 항목 | 내용 |
| --- | --- |
| Method / URL | PUT /api/v1/lost-reports/\{reportId\} |
| 접근 | MEMBER 또는 ADMIN. 별도 소유권 규칙은 아래 참조 |
| Request body | JSON |
| Request model | UpdateLostReportRequest |
| 성공 | 200 LostReportResponse |
| 실패 | 공통 실패, 404 LOST\_REPORT\_NOT\_FOUND, 409 LOST\_REPORT\_NOT\_OPEN |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 인증된 현재 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | string | 아니오 | ko 또는 en. 기본 ko |
| path | reportId | string(UUID) | 예 | 대상 분실 신고 ID |

### 처리 규칙

- 신고자 본인만 OPEN 신고를 수정할 수 있다. 관리자 읽기 권한을 수정 권한으로 확대하지 않는다.
- 등록과 동일한 필드 전체를 교체한다. 누락은 400. 상태·생성일·만료일은 바꾸지 않는다.
- 기존 비활성 참조값을 그대로 유지하는 것은 허용하고 새로 선택하는 카테고리·건물은 활성 상태여야 한다.
- 수정 후 매칭을 다시 계산한다. 새 후보만 신규 알림을 생성한다. privateIdentifyingDetails는 매칭에 사용하지 않는다.

### 요청 예시

```json
{
  "categoryId": "20e550a3-0cbb-419c-99a9-585aa9dadc58",
  "description": "검은색 이어폰 케이스",
  "possibleBuildingIds": [
    "846fe322-488c-424a-977c-bde931ed53de"
  ],
  "lostDateFrom": "2026-11-01",
  "lostDateTo": "2026-11-02",
  "privateIdentifyingDetails": "케이스 안쪽 별 모양 스티커"
}
```

## LOST-05 분실 신고 연장

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/lost-reports/\{reportId\}/extend |
| 접근 | MEMBER 또는 ADMIN. 별도 소유권 규칙은 아래 참조 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 LostReportResponse |
| 실패 | 공통 실패, 404 LOST\_REPORT\_NOT\_FOUND, 409 LOST\_REPORT\_NOT\_OPEN |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 인증된 현재 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Accept-Language | string | 아니오 | ko 또는 en. 기본 ko |
| path | reportId | string(UUID) | 예 | 대상 분실 신고 ID |

### 처리 규칙

- 신고자 본인만 OPEN 신고를 연장할 수 있다.
- 연장 기간은 SRS 미정이므로 30일로 제안한다. 새 expiresAt=max(현재 expiresAt, 요청 시각)+30일.
- 자동 종료와 경합하면 트랜잭션에서 상태를 다시 검사한다. 이미 CLOSED면 409. 재개방·개인정보 복원은 하지 않는다.
- 본문 없음. 기간·상태를 클라이언트가 지정하지 않는다.

## LOST-06 해결 완료 처리

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/lost-reports/\{reportId\}/resolve |
| 접근 | MEMBER 또는 ADMIN. 별도 소유권 규칙은 아래 참조 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 LostReportResponse |
| 실패 | 공통 실패, 404 LOST\_REPORT\_NOT\_FOUND |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 인증된 현재 세션 |
| header | X-CSRF-Token | string | 예 | 현재 세션의 CSRF 토큰 |
| header | Accept-Language | string | 아니오 | ko 또는 en. 기본 ko |
| path | reportId | string(UUID) | 예 | 대상 분실 신고 ID |

### 처리 규칙

- 신고자 본인이 언제든 해결 완료를 표시할 수 있다. OPEN → RESOLVED, 자동 종료된 CLOSED → RESOLVED도 허용한다. 이미 RESOLVED면 현재 상태를 200으로 반환한다.
- 종료 시각·상태를 기록하고 비공개 식별 정보를 즉시 삭제한다. 종료된 신고는 더 이상 매칭 알림을 받지 않는다. 이미 대기 중인 개별·요약 이메일도 발송 전에 제외한다.
- CLOSED → RESOLVED는 상태 표시 변경일 뿐 삭제된 비공개 정보를 되살리거나 보존 기간을 연장하지 않는다.
- 상태 변경을 감사 로그에 기록한다. 본문 없음.

## MATCH-01 내 신고의 매칭 후보 조회

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/lost-reports/\{reportId\}/matches |
| 접근 | MEMBER 또는 ADMIN. 별도 소유권 규칙은 아래 참조 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 MatchCandidatePage |
| 실패 | 공통 실패, 404 LOST\_REPORT\_NOT\_FOUND |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 인증된 현재 세션 |
| header | Accept-Language | string | 아니오 | ko 또는 en. 기본 ko |
| path | reportId | string(UUID) | 예 | 대상 분실 신고 ID |
| query | page | integer | 아니오 | 기본0, 0 이상 |
| query | size | integer | 아니오 | 기본20, 1\~100 |

### 처리 규칙

- 신고자 본인 또는 관리자만 조회 가능. 타 회원은 404.
- 후보를 최초 발견한 시각 matchedAt 내림차순, 동률 candidateId 내림차순. 해당 신고가 종료되어도 보존 중인 기존 후보는 조회할 수 있다.
- 숨겨졌거나 삭제된 습득물은 회원에게 반환하지 않는다. 민감 사진·보관 위치·다운로드 URL·타인의 연락처는 이 응답에 넣지 않는다.
- 후보 응답의 itemId를 사용해 습득물 API로 이동한다. 사진·보관 위치는 습득물 명세의 권한 확인·열람 로그 경로로만 조회한다.
- 목록 조회는 재매칭이나 신규 알림을 발생시키지 않는다.

## Request model

### CreateLostReportRequest / UpdateLostReportRequest

두 모델의 필드 구조는 같다. PUT은 부분 수정이 아니라 아래 전체 필드 교체다.

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| categoryId | string(UUID) | 예 | 카테고리 ID |
| description | string | 예 | trim 후 1\~2000자, 물품 설명 |
| possibleBuildingIds | string(UUID)\[\] | 예 | 중복 없이 1\~100개. 가능한 발견 건물 |
| lostDateFrom | string(date) | 예 | KST 기준 분실 기간 시작일 |
| lostDateTo | string(date) | 예 | lostDateFrom 이상, 오늘 이하 |
| privateIdentifyingDetails | string | 예 | trim 후 1\~1000자. 본인·관리자만 조회하는 식별 정보 |

문자수·건물 수 제한은 초안값이다. lostDateFrom도 오늘 이하여야 한다. 관리자 조회에서 정당한 사유가 없는 타인 연락처를 별도 필드로 수집하지 않는다.

## Response model

### LostReportResponse

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| reportId | string(UUID) | 예 | 신고 ID |
| ownerId | string(UUID) | 예 | 신고자 내부 ID |
| categoryId | string(UUID) | 예 | 카테고리 ID |
| description | string | 예 | 분실물 설명 |
| possibleBuildingIds | string(UUID)\[\] | 예 | 가능한 발견 건물 |
| lostDateFrom / lostDateTo | string(date) | 각 예 | 분실 날짜 범위 |
| privateIdentifyingDetails | string 또는 null | 예 | OPEN에서 본인·관리자만 조회. 종료 즉시 null |
| status | LostReportStatus | 예 | OPEN, RESOLVED, CLOSED |
| analysisStatus | ProcessingStatus | 예 | 현재 신고 공개 설명의 PENDING / PROCESSING / READY / FAILED |
| matchingStatus | ProcessingStatus | 예 | 현재 신고의 비교 대상까지 포함한 매칭 진행 상태 |
| createdAt / updatedAt / expiresAt | string(date-time) | 각 예 | 생성·수정·신고 유효기한 |
| closedAt | string(date-time) 또는 null | 예 | 최초 종료 시각. OPEN이면 null |

```json
{
  "reportId": "b40638c0-9382-4c4a-9af7-9319ba4887f1",
  "ownerId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
  "categoryId": "20e550a3-0cbb-419c-99a9-585aa9dadc58",
  "description": "검은색 이어폰 케이스",
  "possibleBuildingIds": [
    "846fe322-488c-424a-977c-bde931ed53de"
  ],
  "lostDateFrom": "2026-11-01",
  "lostDateTo": "2026-11-02",
  "privateIdentifyingDetails": "케이스 안쪽 별 모양 스티커",
  "status": "OPEN",
  "analysisStatus": "PENDING",
  "matchingStatus": "PENDING",
  "createdAt": "2026-11-02T15:00:00+09:00",
  "updatedAt": "2026-11-02T15:00:00+09:00",
  "expiresAt": "2026-12-02T15:00:00+09:00",
  "closedAt": null
}
```

### LostReportSummary / LostReportPage

LostReportSummary는 LostReportResponse에서 privateIdentifyingDetails만 제외한다. 나머지 필드는 동일하다.

| 모델 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| LostReportPage | items | LostReportSummary\[\] | 예 | 결과 목록 |
| LostReportPage | page / size | integer | 각 예 | 현재 페이지·크기 |
| LostReportPage | totalElements | integer | 예 | 필터 적용 후 전체 건수 |
| LostReportPage | totalPages | integer | 예 | 전체 페이지 수. 빈 결과는0 |

```json
{
  "items": [],
  "page": 0,
  "size": 20,
  "totalElements": 0,
  "totalPages": 0
}
```

### MatchCandidateResponse / MatchCandidatePage

| 모델 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| MatchCandidateResponse | candidateId | string(UUID) | 예 | 후보 ID |
| MatchCandidateResponse | reportId | string(UUID) | 예 | 연결된 신고 |
| MatchCandidateResponse | itemId | string(UUID) | 예 | 연결된 습득물 |
| MatchCandidateResponse | matchedAt | string(date-time) | 예 | 후보 최초 등록 시각 |
| MatchCandidateResponse | matchedBy | string\[\] | 예 | BUILDING 또는 KEYWORD. 두 조건 모두면 둘 다 |
| MatchCandidateResponse | item | MatchItemSummary | 예 | 아래 공개 정보만 포함 |
| MatchItemSummary | itemId / categoryId / foundBuildingId | string(UUID) | 각 예 | 물품·카테고리·발견 건물 ID |
| MatchItemSummary | title | string | 예 | 공개 제목 |
| MatchItemSummary | foundAt | string(date-time) | 예 | 발견 시각 |
| MatchItemSummary | status | FoundItemStatus | 예 | POSTED, COLLECTED, EXPIRED |
| MatchItemSummary | sensitive | boolean | 예 | 민감 물품 여부 |
| MatchCandidatePage | items | MatchCandidateResponse\[\] | 예 | 후보 목록 |
| MatchCandidatePage | analysisStatus / matchingStatus | ProcessingStatus | 각 예 | 신고 설명 분석 상태 / 비교 범위를 포함한 매칭 상태 |
| MatchCandidatePage | isComplete | boolean | 예 | matchingStatus=READY일 때만 true. false인 목록·개수는 최종 결과가 아님 |
| MatchCandidatePage | page / size / totalElements / totalPages | 페이지 모델과 동일 | 각 예 | LostReportPage와 동일한 페이지 필드 |

MatchItemSummary는 습득물 공개 요약의 부분 집합이다. 사진·보관 위치는 별도 권한 경로로만 조회하며 타인의 비공개 신고 정보·연락처를 포함하지 않는다.

```json
{
  "items": [
    {
      "candidateId": "52428993-c955-4968-8b31-e97d3aa1197d",
      "reportId": "b40638c0-9382-4c4a-9af7-9319ba4887f1",
      "itemId": "dab45e58-34af-4ba7-90cb-59471cc17a13",
      "matchedAt": "2026-11-02T15:00:01+09:00",
      "matchedBy": [
        "BUILDING"
      ],
      "item": {
        "itemId": "dab45e58-34af-4ba7-90cb-59471cc17a13",
        "categoryId": "20e550a3-0cbb-419c-99a9-585aa9dadc58",
        "foundBuildingId": "846fe322-488c-424a-977c-bde931ed53de",
        "title": "이어폰 케이스를 주웠습니다",
        "foundAt": "2026-11-02T14:00:00+09:00",
        "status": "POSTED",
        "sensitive": false
      }
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1,
  "analysisStatus": "READY",
  "matchingStatus": "READY",
  "isComplete": true
}
```

## 서버 내부 매칭·자동 종료 계약

### 비동기 진행 상태 (2026-11-08)

ProcessingStatus는 PENDING(대기), PROCESSING(실행/재평가 중), READY(해당 범위 완료), FAILED(실패)다. 내부 SUPERSEDED를 외부에 반환하지 않는다. analysisStatus는 신고 자신의 현재 공개 설명만, matchingStatus는 현재 비교 범위의 분석·재평가까지 포함한다. 범위에 실패가 있으면 FAILED, 그 외 PROCESSING, PENDING, READY 순으로 집계한다. isComplete는 matchingStatus=READY일 때만 true다. 실패·대기 중 빈 목록을 확정된 일치 없음으로 표시하지 않는다.

처리 중 items·totalElements·totalPages는 현재 유효한 결과 기준이며 최종 목록·총수가 아니다. 페이지와 후보 정렬은 기존 규칙을 유지한다. 후보 조회는 재평가·모델 실행·알림 생성의 부작용이 없다. 종료 신고는 새 분석을 요청하지 않고 보존 이력을 제공한다. 이 경우 matchingStatus=READY와 isComplete=true는 이력 조회 완료를 뜻하며 analysisStatus는 마지막 보존 상태를 유지한다. 숨김·삭제·인가 규칙은 이력에도 적용한다. 번역문·키워드·모델 경로·내부 오류를 응답하지 않는다.

LostReportSummary는 위 두 상태 필드를 포함하며 privateIdentifyingDetails만 제외한다. 공통 DTO는 schema/matching.py, 쿼리 모델은 schema/matching_params.py다. 상태 집계 서비스와 실제 MATCH-01 라우터 연동은 아직 구현 전이다. 트랜잭션·이벤트 연결은 [API 팀 인계](../design/translation-keyword-implementation-plan.md)를 따른다.

| 항목 | 규칙 |
| --- | --- |
| 매칭 실행 | 습득물 또는 분실 신고 생성·수정마다 실행. 별도의 회원용 수동 매칭 생성 API 없음 |
| 필수 조건1 | 습득물 categoryId = 분실 신고 categoryId |
| 필수 조건2 | 습득물 foundAt의 KST 날짜 >= lostDateFrom |
| 필수 조건3 | foundBuildingId가 possibleBuildingIds에 포함되거나 공개 제목·설명에 공통 키워드 존재 |
| 날짜 상한 | lostDateTo를 발견일 상한으로 사용하지 않음. SRS FR-16에 해당 조건 없음 |
| 키워드 비교 | 공개 한국어 제목·설명을 Helsinki-NLP/opus-mt_tiny_kor-eng로 영어 번역 후 정규화·구문/동의어 규칙으로 canonical 키워드 비교. 영어는 번역 생략. 비공개 정보 미사용. 일반 검색·구독 규칙은 변경하지 않음 |
| 비동기 실행 | 원본과 분석·재평가 요청은 같은 트랜잭션. 모델 추론은 요청 밖 전용 스레드. 현재 원본/분석/정책 버전을 확인한 결과만 노출 |
| 후보 유일성 | reportId+itemId 유일. 재시도·동시 수정에도 후보와 신규 알림 중복 생성 방지 |
| 수정 후 불일치 | 조건을 잃은 현재 후보 연결 제거 제안. 동일 쌍 재등장 알림은 최초 후보 발생 이력 기준 중복 억제 |
| 후보와 가용성 | FR-16의 세 조건 자체에는 상태 조건을 추가하지 않음. 숨김·종료 물품은 검색 기본값·응답 권한·알림 발송 가능성을 별도로 처리 |
| 신고 종료 후 | 기존 후보 조회 가능, 신규 매칭 알림 중단. 종료 신고에서 후보 계산 여부는 구현 정책으로 분리하되 사용자에게 추가 알림 없음 |
| 수거 연동 FR-22 | 수거 트랜잭션에서 수거자 소유이며 수거 물품을 현재 후보로 가진 OPEN 신고 모두 RESOLVED 처리. 한 신고만 임의로 선택하지 않음 |
| 수거 판정 대기 | 필요한 최신 분석 미완료면 409 MATCHING_PENDING으로 수거 전체를 거절. 최신 분석과 카테고리 잠금으로 현재 후보 집합을 다시 검증 |
| 비수거자의 신고 | 같은 물품을 후보로 가진 다른 회원 신고는 자동 종료하지 않음 |
| 취소 연동 | 잘못된 수거를 취소해도 종료 신고·삭제 개인정보를 자동 복구하지 않음. 새 신고가 필요한 정책은 제안사항 |
| 자동 종료 FR-11 | 생성 후30일, 연장하면 변경된 expiresAt에 도달한 OPEN 신고를 CLOSED로 변경 |
| 자동 종료 실행 | 저사용 시간 일일 작업. API 접근 시에도 만료 경계의 일관성을 보장하도록 검사. 종료·연장 경합은 상태 잠금·조건부 갱신 |
| 상태 감사 | OPEN 생성, CLOSED 자동 종료, RESOLVED 해결·수거 종료 등 상태 변경에 행위자(자동 작업이면 SYSTEM)·시각·대상 기록 |
| 삭제 | 종료 즉시 privateIdentifyingDetails를 DB·검색 인덱스·알림 큐 등 활성 저장소에서 제거. 로그에 원문 미기록 |
| 보존 | 나머지 신고 정보1년. 초안은 최초 closedAt부터1년으로 해석. 연결된 신고나 물품 영구 삭제 시 후보 함께 삭제 |
| 백업 | 삭제 데이터가 복원으로 재노출되지 않도록 삭제 반영·복구 후 정리. 정확한 백업 보존·삭제 정책은 운영 명세에서 확정 |

## 오류·검증 기준

추가 오류는 400 INVALID\_REFERENCE(존재하지 않거나 새로 선택할 수 없는 기준정보), 404 LOST\_REPORT\_NOT\_FOUND(없음 또는 소유권 없음), 409 LOST\_REPORT\_NOT\_OPEN(수정·연장 불가능 상태)다. 실패 시 상태·기한·매칭을 부분 반영하지 않는다.

| 확인 상황 | 기대 결과 |
| --- | --- |
| 날짜 시작 > 종료 또는 종료 > 오늘 | 400 필드 오류 |
| 타인 상세·매칭·수정·연장·해결 요청 | 404, privateIdentifyingDetails 노출 없음 |
| 관리자 상세 조회 | 허용. 신고자 아닌 관리자의 수정·연장·해결은 불허 |
| 매칭 세 조건 중 하나 불만족 | 후보 생성 없음 |
| 발견일이 lostDateTo 이후이나 세 조건 충족 | 후보 생성 가능. 날짜 상한 추가 금지 |
| 생성·수정 이벤트 재처리 | 후보·신규 알림 중복 없음 |
| OPEN → RESOLVED / CLOSED | 식별 정보 즉시 삭제, 신규·대기 매칭 이메일 중단 |
| CLOSED → RESOLVED | 소유자 요청 허용, 삭제 개인정보 복원 없음 |
| 한 물품 수거자가 관련 OPEN 신고 여러 개 보유 | 해당 수거자의 연결 신고 모두 종료, 타인 신고 유지 |
| 민감 물품 후보 조회 | 사진·보관 위치·직접 URL 없음. 별도 습득물 경로로 접근 |

## 명시적 설계 제안·미정 사항

30일 단위 연장, 최초 closedAt부터1년 보존, 문자열·건물 수 제한, 키워드 정규화, 불일치 후보 제거·재등장 중복 알림 정책은 SRS가 세부적으로 정하지 않은 초안이다. 상태값 CLOSED는 30일 자동 종료를 표현하기 위한 새 명칭이다. 사용자 소유권 승인·찾은 사람 사전 승인 절차는 추가하지 않는다.

