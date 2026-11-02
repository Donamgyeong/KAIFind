# 인증

> 원문: [Notion](https://app.notion.com/p/40c23542cf8c819c8546c332565ea720?pvs=204) · 내보낸 날짜: 2026-11-02 (KST)

## 범위와 설계 전제

학교 SSO에 실제 연결하지 않고 서버에 사전 등록한 가상 계정으로 로그인한다. 사용자 요청에 따라 SRS FR-1의 외부 인증 연동을 목업으로 대체한다. 비밀번호는 입력받거나 저장하지 않는다.

이 문서는 API 설계 초안이다. 아래 경로, DTO, 쿠키 이름, 만료 시간은 새로 제안한 값이며 기존 구현 또는 SRS 확정값을 뜻하지 않는다.

### 요청·응답 형식

| 항목 | 설계 |
| --- | --- |
| Base URL | /api/v1 |
| 요청·응답 | application/json. 204 응답에는 본문 없음 |

### 인증·권한·적용 범위

| 항목 | 설계 |
| --- | --- |
| 인증 방식 | 서버 세션 + HttpOnly 쿠키 |
| 배포 형태 | 프런트엔드와 API를 동일 origin에서 제공하는 구성을 기본으로 함 |
| 역할 | MEMBER, ADMIN. ADMIN은 일반 회원 기능도 사용 가능 |
| 비회원 | 계정 역할값이 아니라 유효한 로그인 세션이 없는 상태 |
| 신규 가입 | 별도 가입 API 없음. 서버의 가상 계정과 로컬 사용자를 연결하고 첫 로그인 시 로컬 사용자 생성 |
| 사용자 식별 | 외부 식별자인 mockSubject를 서버 내부에서 고정 관리. API의 userId는 서비스 UUID |
| 목업 사용 환경 | local, test, demo에서 명시적으로 활성화. 실제 운영에서는 계정 목록·목업 로그인 API를 404로 비활성화 |
| 관리자 계정 | 서버 seed로만 지정. 로그인 요청에서 역할·이메일·이름을 전달해 변경할 수 없음 |
| 범위 제외 | 비밀번호 로그인·재설정, 실제 SSO 리다이렉트·콜백, JWT 재발급, 회원 탈퇴, 프로필 수정 |
| 별도 명세 대상 | FR-3 관리자 권한 부여·회수는 관리자 API에서 정의. 실제 권한은 서버의 현재 사용자 데이터로 확인 |

### 세션·보존 기간

| 항목 | 설계 |
| --- | --- |
| 만료 제안 | 미활동 30분 또는 로그인 후 12시간 중 먼저 도달한 시점 |

SRS 연결: FR-1 로그인·비밀번호 미저장, FR-2 비회원 제한, FR-3 역할, SI-1 사용자 식별 정보, SEC-1 세션 만료, SEC-2 서버 권한 검사, SEC-3 연락처 비공개. 실제 학교 신원 검증은 수행하지 않으므로 목업 로그인은 학교 계정 소유를 증명하지 않는다.

## 1. 엔드포인트 목록

### 세션·CSRF·로그아웃

| ID | Method | Endpoint | 기능 |
| --- | --- | --- | --- |
| AUTH-01 | GET | <code>/api/v1/auth/csrf</code> | CSRF 토큰 발급·조회 |
| AUTH-04 | GET | <code>/api/v1/auth/me</code> | 로그인한 본인 조회 |
| AUTH-05 | POST | <code>/api/v1/auth/logout</code> | 현재 세션 로그아웃 |

| ID | 인증 | Request model | Response model |
| --- | --- | --- | --- |
| AUTH-01 | 불필요 | 없음 | CsrfTokenResponse |
| AUTH-04 | 필요 | 없음 | AuthUserResponse |
| AUTH-05 | 선택, CSRF 필요 | 없음 | 없음, 204 |

### 목업 계정·로그인

| ID | Method | Endpoint | 기능 |
| --- | --- | --- | --- |
| AUTH-02 | GET | <code>/api/v1/auth/mock/accounts</code> | 선택 가능한 가상 계정 조회 |
| AUTH-03 | POST | <code>/api/v1/auth/mock/login</code> | 선택 계정 로그인 |

| ID | 인증 | Request model | Response model |
| --- | --- | --- | --- |
| AUTH-02 | 불필요, 목업 환경 전용 | 없음 | MockAccountListResponse |
| AUTH-03 | 불필요, CSRF 필요, 목업 환경 전용 | MockLoginRequest | LoginResponse |

경로·쿼리 파라미터는 모든 엔드포인트에서 없다. 아래 Parameter 표의 위치는 header 또는 cookie를 뜻한다.

## 2. 공통 인증·세션 규칙

### 인증·권한·적용 범위

| 항목 | 규칙 |
| --- | --- |
| 세션 쿠키 | KAIFIND\_SESSION. 서버가 발급한 추측 불가능한 세션 식별자 |
| 쿠키 속성 | HttpOnly; Secure; SameSite=Lax; Path=/; Domain 미지정 |
| HTTPS 적용 범위 | local·test·demo를 포함한 브라우저·API 통신은 HTTPS를 사용하고 Secure=true를 유지한다. HTTP 예외는 현행 SRS에 포함하지 않는다. |
| 세션 저장 | 사용자 ID, 생성 시각, 마지막 활동 시각, CSRF 검증 정보를 서버에서 관리 |
| 인증 헤더 | Authorization Bearer 사용 안 함. 브라우저가 Cookie 전송 |
| 세션 재발급 | 로그인 성공 시 기존 세션을 폐기하고 새 식별자·CSRF 토큰 발급 |
| 권한 확인 | 요청마다 서버에서 역할·리소스 소유권 검사. 클라이언트 전달 role은 신뢰하지 않음 |
| CSRF | 로그인·로그아웃을 포함한 상태 변경 요청은 X-CSRF-Token 검증. 유효하지 않으면 403 |
| CSRF 생명주기 | AUTH-01이 익명 또는 로그인 세션에 연결된 토큰 반환. 로그인 성공 시 교체되며 LoginResponse에 새 토큰 반환 |
| Origin | 상태 변경 요청의 Origin이 있으면 서버의 허용 origin과 일치해야 함 |
| 엄격한 요청 검증 | 정의되지 않은 JSON 필드, null, 잘못된 타입을 거부 |
| 남용 제한 제안 | 목업 로그인은 IP당 1분 30회, 초과 시 429와 Retry-After 헤더 |

### 세션·보존 기간

| 항목 | 규칙 |
| --- | --- |
| 쿠키 수명 | 세션 쿠키로 발급. 서버의 30분 미활동·12시간 절대 만료를 별도로 적용 |
| 미활동 기준 | 인증 성공한 보호 API 요청 시 lastActivityAt 갱신. CSRF 발급·계정 목록 조회는 갱신하지 않음 |

### 요청·응답 형식

| 항목 | 규칙 |
| --- | --- |
| 만료 응답 | 보호 API는 401 SESSION\_EXPIRED. 만료 쿠키 삭제. 세션 정보가 이미 제거되어 원인을 판별할 수 없으면 401 AUTH\_REQUIRED |
| 캐시 | 모든 인증 응답에 Cache-Control: no-store |
| 시간 | RFC 3339, KST 오프셋 포함. 예: 2026-11-02T15:00\:00+09\:00 |

### 개인정보·접근 제어

| 항목 | 규칙 |
| --- | --- |
| 데이터 노출 | 본인 조회 응답에만 본인 이메일 제공. 계정 선택 목록에는 이메일·전화번호 미포함 |

동일 origin에서는 브라우저가 쿠키를 함께 보낸다. 별도 origin 개발 서버 사용 시 credentials: "include", 명시적 허용 origin, credentials 허용 CORS 설정이 필요하다. 임의의 origin 허용 및 wildcard origin과 credentials의 조합은 사용하지 않는다.

## 3. AUTH-01 CSRF 토큰 발급·조회

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/auth/csrf |
| 목적 | 로그인 전 또는 페이지 새로고침 후 CSRF 토큰 확보 |
| 접근 | 비회원·회원 |
| Path / Query parameter | 없음 |
| Request body / model | 없음 |
| 성공 | 200 CsrfTokenResponse |
| 부수 효과 | 세션이 없으면 익명 세션 생성 및 쿠키 발급. 로그인 상태 자체는 변경하지 않음 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 아니오 | 있으면 해당 세션의 CSRF 토큰 반환 |

### Response model: CsrfTokenResponse

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| csrfToken | string | 예 | 현재 세션에 연결된 opaque 토큰 |
| headerName | string | 예 | 고정값 X-CSRF-Token |

```json
{
  "csrfToken": "example-csrf-token",
  "headerName": "X-CSRF-Token"
}
```

토큰은 브라우저 메모리에 보관한다. 로그인·로그아웃 후 과거 토큰을 재사용하지 않는다.

## 4. AUTH-02 목업 계정 목록 조회

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/auth/mock/accounts |
| 목적 | 로그인 화면에 서버가 허용한 가상 계정 목록 표시 |
| 접근 | 목업 기능이 활성화된 환경의 모든 사용자 |
| Path / Query parameter | 없음 |
| Parameter | 없음 |
| Request body / model | 없음 |
| 성공 | 200 MockAccountListResponse |
| 실패 | 404 MOCK\_AUTH\_DISABLED |

### Response model: MockAccountListResponse

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| accounts | MockAccountSummary\[\] | 예 | 서버에서 활성화한 테스트 계정 목록. 없으면 빈 배열 |

### Model: MockAccountSummary

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| mockAccountId | string | 예 | 로그인 요청에 사용하는 안정적인 가상 계정 키 |
| displayName | string | 예 | 화면 표시용 가상 이름 |
| affiliation | Affiliation | 예 | STUDENT, FACULTY, STAFF |
| role | Role | 예 | 현재 로컬 역할. 첫 로그인 전에는 seed 역할 |

```json
{
  "accounts": [
    {
      "mockAccountId": "student-01",
      "displayName": "테스트 학생 1",
      "affiliation": "STUDENT",
      "role": "MEMBER"
    },
    {
      "mockAccountId": "admin-01",
      "displayName": "테스트 관리자",
      "affiliation": "STAFF",
      "role": "ADMIN"
    }
  ]
}
```

관리자 계정을 선택할 수 있는 것은 격리된 데모의 의도된 동작이다. 모든 계정 데이터는 합성 데이터이며 실제 학생 정보나 실제 수신자 이메일을 사용하지 않는다. 이메일 예시는 예약 도메인 [example.com](http://example.com)을 사용하고 알림은 테스트 메일 수신함으로 라우팅한다.

## 5. AUTH-03 목업 로그인

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/auth/mock/login |
| 목적 | 가상 계정에 연결된 사용자를 조회·생성하고 로그인 세션 발급 |
| 접근 | 목업 기능이 활성화된 환경. AUTH-01로 CSRF 토큰을 먼저 발급받아야 함 |
| Path / Query parameter | 없음 |
| Request body | JSON |
| Request model | MockLoginRequest |
| 성공 | 200 LoginResponse, Set-Cookie로 새 세션 발급 |
| 실패 | 400 VALIDATION\_ERROR / MALFORMED\_JSON, 401 INVALID\_MOCK\_ACCOUNT, 403 CSRF\_INVALID / ORIGIN\_NOT\_ALLOWED, 404 MOCK\_AUTH\_DISABLED, 415 UNSUPPORTED\_MEDIA\_TYPE, 429 RATE\_LIMITED |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| header | Content-Type | string | 예 | application/json |
| header | X-CSRF-Token | string | 예 | AUTH-01에서 발급받은 토큰 |
| cookie | KAIFIND\_SESSION | string | 예 | 해당 토큰을 발급받은 익명 또는 로그인 세션 |

### Request model: MockLoginRequest

| 필드 | 타입 | 필수 | 검증 | 설명 |
| --- | --- | --- | --- | --- |
| mockAccountId | string | 예 | 1\~64자, 패턴 \^\[a-z0-9\]\[a-z0-9\_-\]\{0,63\}\$ | 서버가 미리 등록한 계정 키 |

```json
{
  "mockAccountId": "student-01"
}
```

userId, name, email, affiliation, role은 요청 필드가 아니다. 전달하면 400 VALIDATION\_ERROR로 거부한다.

### 처리 규칙

1. 목업 활성화 여부와 요청의 origin·CSRF·형식을 검증한다.
2. mockAccountId가 서버의 활성 계정에 있는지 확인한다. 없는 계정은 생성하지 않고 401을 반환한다.
3. 고정 mockSubject로 로컬 사용자를 조회한다. 처음이면 한 번 생성한다. 동시 첫 로그인에서도 유일성 제약으로 중복 생성하지 않는다.
4. 최초 생성 시 seed 역할을 부여한다. 이후 로그인에서는 관리자가 변경한 역할을 유지한다.
5. 기존 브라우저 세션을 폐기하고 새 로그인 세션과 CSRF 토큰을 발급한다.
6. 사용자가 이미 로그인한 상태라면 선택한 계정으로 전환한다. 다른 브라우저·기기의 세션은 유지한다.
7. 로그인 검증 실패 시 기존 로그인 세션은 유지한다.

### Response model: LoginResponse

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| user | AuthUserResponse | 예 | 로그인 사용자 정보 |
| isNewUser | boolean | 예 | 이번 요청으로 로컬 사용자가 처음 생성되었는지 |
| session | SessionInfo | 예 | 발급 시점의 만료 정보 |
| csrfToken | string | 예 | 새 세션의 CSRF 토큰. 이전 토큰 대체 |

```json
{
  "user": {
    "userId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
    "name": "테스트 학생 1",
    "email": "student01@example.com",
    "affiliation": "STUDENT",
    "role": "MEMBER",
    "language": "ko"
  },
  "isNewUser": true,
  "session": {
    "idleTimeoutSeconds": 1800,
    "idleExpiresAt": "2026-11-02T15:30:00+09:00",
    "absoluteExpiresAt": "2026-11-03T03:00:00+09:00"
  },
  "csrfToken": "example-new-csrf-token"
}
```

세션 식별자는 JSON에 포함하지 않는다. Set-Cookie로만 전달한다. idleExpiresAt은 발급 시점의 값이며 이후 인증된 활동에 따라 갱신되고 absoluteExpiresAt을 초과하지 않는다.

## 6. AUTH-04 내 인증 정보 조회

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/auth/me |
| 목적 | 새로고침 시 로그인 상태 복원 및 본인 정보·현재 역할 확인 |
| 접근 | 로그인 회원·관리자 |
| Path / Query parameter | 없음 |
| Request body / model | 없음 |
| 성공 | 200 AuthUserResponse |
| 실패 | 401 AUTH\_REQUIRED / SESSION\_EXPIRED |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효한 로그인 세션 |

### Response model: AuthUserResponse

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| userId | string, UUID | 예 | 서비스 내부 사용자 ID |
| name | string | 예 | 가상 SSO에서 제공한 이름 |
| email | string, email | 예 | 본인의 가상 이메일. 다른 회원 조회용 모델에 재사용 금지 |
| affiliation | Affiliation | 예 | STUDENT, FACULTY, STAFF |
| role | Role | 예 | MEMBER, ADMIN. 현재 DB 값 |
| language | Language | 예 | ko, en. 최초 생성 기본값 ko |

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

비회원에게 200과 user:null을 반환하지 않는다. 401을 받은 프런트엔드는 비회원 화면으로 전환한다. role은 UI 표시용으로 사용할 수 있지만 API 접근 허용 여부는 항상 서버에서 판정한다.

## 7. AUTH-05 로그아웃

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/auth/logout |
| 목적 | 현재 브라우저 세션 폐기 |
| 접근 | 로그인 또는 유효한 익명 CSRF 세션 |
| Path / Query parameter | 없음 |
| Request body / model | 없음. \{\}도 보내지 않음 |
| 성공 | 204 No Content |
| 실패 | 403 CSRF\_INVALID / ORIGIN\_NOT\_ALLOWED |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| header | X-CSRF-Token | string | 예 | 현재 세션에 연결된 토큰 |
| cookie | KAIFIND\_SESSION | string | 예 | 토큰이 연결된 세션 |

### 처리와 응답

- 서버의 현재 세션을 폐기하고 같은 Path·쿠키 속성으로 Max-Age=0을 설정해 쿠키를 삭제한다.
- 본문과 새 CSRF 토큰을 반환하지 않는다.
- 다른 기기·브라우저 세션은 폐기하지 않는다.
- 유효한 익명 세션에서 호출해도 204를 반환한다.
- 세션 만료·삭제로 CSRF 검증이 불가능하면 403이다. 클라이언트는 AUTH-01을 호출해 새 익명 세션·토큰을 받은 뒤 재요청할 수 있다.
- 다음 로그인은 AUTH-01부터 다시 수행한다.

## 8. 공통 모델

### Enum

| 모델 | 값 | 의미 |
| --- | --- | --- |
| Role | MEMBER, ADMIN | 일반 회원, 관리자 |
| Affiliation | STUDENT, FACULTY, STAFF | 학생, 교수, 직원 |
| Language | ko, en | 한국어, 영어 |

### SessionInfo

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| idleTimeoutSeconds | integer | 예 | 제안값 1800 |
| idleExpiresAt | string, date-time | 예 | 현재 시점의 미활동 만료 예상 시각 |
| absoluteExpiresAt | string, date-time | 예 | 활동과 무관한 세션 최종 만료 시각 |

### ErrorResponse

성공 응답은 각 모델을 직접 반환한다. 실패 응답만 아래 공통 구조를 사용한다.

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| code | string | 예 | 프런트엔드 분기용 안정적인 오류 코드 |
| message | string | 예 | 사용자용 메시지 |
| fieldErrors | FieldError\[\] | 예 | 필드 검증 오류 목록. 없으면 \[\] |

### FieldError

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| field | string | 예 | 잘못된 필드명 |
| code | string | 예 | REQUIRED, INVALID\_FORMAT, INVALID\_TYPE, UNKNOWN\_FIELD 등 |
| message | string | 예 | 필드 옆에 표시할 오류 메시지 |

```json
{
  "code": "VALIDATION_ERROR",
  "message": "입력값을 확인해주세요.",
  "fieldErrors": [
    {
      "field": "mockAccountId",
      "code": "REQUIRED",
      "message": "로그인할 테스트 계정을 선택해주세요."
    }
  ]
}
```

### 공통 오류 코드

| HTTP | code | 조건 |
| --- | --- | --- |
| 400 | MALFORMED\_JSON | JSON 구문 오류 |
| 400 | VALIDATION\_ERROR | 필수값 누락, null, 타입·형식 오류, 미정의 필드 |
| 401 | AUTH\_REQUIRED | 로그인 세션 없음 또는 식별 불가 |
| 401 | SESSION\_EXPIRED | 미활동 또는 절대 만료 |
| 401 | INVALID\_MOCK\_ACCOUNT | 등록되지 않았거나 비활성화된 가상 계정 |
| 403 | CSRF\_INVALID | CSRF 토큰 누락·불일치·연결 세션 없음 |
| 403 | ORIGIN\_NOT\_ALLOWED | 허용되지 않은 origin |
| 403 | FORBIDDEN | 로그인했지만 해당 작업의 권한 없음. 다른 보호 API에도 공통 적용 |
| 404 | MOCK\_AUTH\_DISABLED | 목업 인증 비활성화 |
| 415 | UNSUPPORTED\_MEDIA\_TYPE | 로그인 요청이 application/json이 아님 |
| 429 | RATE\_LIMITED | 로그인 빈도 제한. Retry-After는 재시도까지 남은 초 |
| 500 | INTERNAL\_SERVER\_ERROR | 예기치 않은 서버 오류. 내부 예외·세션 정보는 노출하지 않음 |

에러 메시지 언어는 모든 엔드포인트의 선택 헤더 Accept-Language: ko 또는 en으로 선택한다. 미지원·누락 값은 ko로 처리한다. code와 fieldErrors\[\].code는 언어와 무관하게 유지한다. 언어 협상이 적용된 응답에는 Content-Language를 반환한다.

## 9. 프런트엔드 호출 순서

1. GET /auth/mock/accounts로 가상 계정 목록을 표시한다.
2. GET /auth/csrf로 익명 세션 쿠키·CSRF 토큰을 받는다.
3. 선택한 mockAccountId와 X-CSRF-Token으로 POST /auth/mock/login을 호출한다.
4. 응답의 user로 화면을 갱신하고 csrfToken을 새 값으로 교체한다.
5. 새로고침 시 GET /auth/me로 로그인 여부를 확인하고 GET /auth/csrf로 현재 세션의 토큰을 다시 받는다.
6. 이후 상태 변경 API는 세션 쿠키와 X-CSRF-Token을 함께 사용한다.
7. POST /auth/logout 성공 시 사용자 정보와 메모리의 CSRF 토큰을 비운다.

## 10. 구현 확인 기준

| 상황 | 기대 결과 |
| --- | --- |
| 유효한 가상 계정 첫 로그인 | 200, isNewUser=true, 사용자 1개 생성, 새 세션·토큰 |
| 같은 계정 재로그인 | 기존 userId, isNewUser=false, 세션·토큰 교체 |
| 로그인 요청에 role=ADMIN 추가 | 400, 관리자 권한 상승 없음 |
| 없는 계정 선택 | 401, 사용자 생성 없음, 기존 로그인 유지 |
| CSRF 없이 로그인·로그아웃 | 403 |
| 비회원 /auth/me | 401 |
| 유효 세션 /auth/me | 200, 현재 DB 역할 반환 |
| 미활동 30분 또는 12시간 도달 | 보호 API 접근 거절 |
| 로그아웃 후 기존 세션 재사용 | 인증 실패 |
| 관리자가 역할 변경 후 재로그인 | 변경된 역할 유지, seed로 덮어쓰지 않음 |
| 목업 비활성화 | /auth/mock/accounts와 /auth/mock/login 모두 404 |
| 연락처 노출 | 계정 목록에 이메일·전화번호 없음. /auth/me에는 본인 이메일만 포함 |

## 11. 추후 조정할 설계값

- 세션 미활동 30분·절대 12시간은 SRS 미정 사항에 대한 초안값이다.
- 로그인 제한은 IP당 분당 30회로 제안한다.
- 이 문서는 세션 방식을 제안한다. JWT 방식으로 바꾸려면 로그인·로그아웃·재발급·보관 정책을 함께 개정해야 한다.
- 실제 SSO를 도입할 경우 목업 계정 선택 부분을 교체하고 회원·권한·세션에 대한 나머지 계약을 유지하는 방향으로 설계한다.

