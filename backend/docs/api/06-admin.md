# 관리자

> 원문: [Notion](https://app.notion.com/p/40c23542cf8c81b89a3fc6be168267db?pvs=204) · 내보낸 날짜: 2026-11-02 (KST)

## 범위와 우선순위

| 구분 | SRS | 기능 |
| --- | --- | --- |
| Must | FR-3, FR-27, FR-30 | 관리자 권한, 기준정보 관리, 감사 기록 |
| Should | FR-23, FR-28, FR-29 | 수거 분쟁 검토, 통계, 게시물 신고·숨김 |

MOD-01은 로그인 회원 공통 API이고 나머지는 ADMIN만 사용한다. 상세 경로·필드 길이·분쟁 결과값·보존 기산점은 설계 제안이며 구현 완료를 뜻하지 않는다.

공통 세션·오류는 [인증](01-auth.md), 전체 공통 계약은 [공통 규칙·운영 요구사항](00-common.md)을 따른다.

## 공통 요청·응답 규칙

### 인증과 요청

| 항목 | 규칙 |
| --- | --- |
| Base URL | <code>/api/v1</code> |
| 통신 | HTTPS |
| 인증 | <code>KAIFIND_SESSION</code> 쿠키 |
| 쓰기 요청 | <code>X-CSRF-Token</code> 및 허용 Origin 검사 |
| JSON 본문 | <code>Content-Type: application/json</code> |
| 인가 | 현재 서버 DB 권한 기준. 클라이언트가 userId·role로 인증 주체를 지정할 수 없음 |
| 입력 검증 | 미정의 JSON 필드·null·잘못된 타입 거부 |
| PATCH | 최소 한 필드 필수, 생략한 필드는 유지 |

### 데이터 형식과 응답

| 항목 | 규칙 |
| --- | --- |
| ID | UUID 문자열 |
| 시각 | RFC 3339, KST <code>+09:00</code> |
| 캐시 | <code>Cache-Control: no-store</code> |
| 언어 | Accept-Language: ko/en, 기본 ko |
| 오류 메시지 | 선택 언어로 반환. Content-Language 표시 |

### 페이지네이션

<code>Page[T]</code>에서 T는 해당 목록의 응답 모델이다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| items | T 배열 | 결과 목록 |
| page | integer | 기본 0, 최솟값 0 |
| size | integer | 기본 20, 범위 1\~100 |
| totalElements | integer | 전체 결과 수 |
| totalPages | integer | 전체 페이지 수 |

### 공통 오류

각 API의 추가 실패와 함께 아래 오류를 적용한다.

| HTTP | 오류 코드 |
| --- | --- |
| 400 | VALIDATION\_ERROR, MALFORMED\_JSON |
| 401 | AUTH\_REQUIRED, SESSION\_EXPIRED |
| 403 | FORBIDDEN, CSRF\_INVALID, ORIGIN\_NOT\_ALLOWED |
| 404 | NOT\_FOUND |
| 415 | UNSUPPORTED\_MEDIA\_TYPE |
| 500 | INTERNAL\_SERVER\_ERROR |

### 오류 응답 모델

| 모델 | 필드 | 타입 |
| --- | --- | --- |
| ErrorResponse | code | string |
| ErrorResponse | message | string |
| ErrorResponse | fieldErrors | FieldError 배열 |
| FieldError | field: string; code: string; message: string. 필드 오류가 없으면 빈 배열 |  |
| FieldError | field: string; code: string; message: string. 필드 오류가 없으면 빈 배열 |  |
| FieldError | field: string; code: string; message: string. 필드 오류가 없으면 빈 배열 |  |

## 엔드포인트 목록

### 계정·권한

| ID | Method | Endpoint(Base URL 제외) | 기능 |
| --- | --- | --- | --- |
| ADM-01 | GET | <code>/admin/users</code> | 권한 관리용 회원 조회 |
| ADM-02 | PATCH | <code>/admin/users/{userId}/role</code> | 관리자 권한 부여·회수 |

| ID | Request model | 성공 |
| --- | --- | --- |
| ADM-01 | 없음 | 200 Page\[AdminUserSummary\] |
| ADM-02 | UpdateRoleRequest | 200 AdminUserSummary |

### 건물

| ID | Method | Endpoint(Base URL 제외) | 기능 |
| --- | --- | --- | --- |
| REF-01 | GET | <code>/admin/buildings</code> | 건물 전체 목록 |
| REF-02 | POST | <code>/admin/buildings</code> | 건물 추가 |
| REF-03 | PATCH | <code>/admin/buildings/{buildingId}</code> | 건물 이름 변경·비활성화 |

| ID | Request model | 성공 |
| --- | --- | --- |
| REF-01 | 없음 | 200 Page\[BuildingResponse\] |
| REF-02 | CreateBuildingRequest | 201 BuildingResponse |
| REF-03 | UpdateBuildingRequest | 200 BuildingResponse |

### 카테고리

| ID | Method | Endpoint(Base URL 제외) | 기능 |
| --- | --- | --- | --- |
| REF-04 | GET | <code>/admin/categories</code> | 카테고리 전체 목록 |
| REF-05 | POST | <code>/admin/categories</code> | 카테고리 추가 |
| REF-06 | PATCH | <code>/admin/categories/{categoryId}</code> | 카테고리 이름 변경·비활성화 |

| ID | Request model | 성공 |
| --- | --- | --- |
| REF-04 | 없음 | 200 Page\[CategoryResponse\] |
| REF-05 | CreateCategoryRequest | 201 CategoryResponse |
| REF-06 | UpdateCategoryRequest | 200 CategoryResponse |

### 게시물 신고·검토

| ID | Method | Endpoint(Base URL 제외) | 기능 |
| --- | --- | --- | --- |
| MOD-01 | POST | <code>/found-items/{itemId}/reports</code> | 부적절한 게시물 신고 |
| MOD-02 | GET | <code>/admin/post-reports</code> | 게시물 신고 목록 |
| MOD-03 | GET | <code>/admin/post-reports/{reportId}</code> | 게시물 신고 상세 |
| MOD-04 | POST | <code>/admin/post-reports/{reportId}/review</code> | 신고 검토·숨김 |

| ID | Request model | 성공 |
| --- | --- | --- |
| MOD-01 | CreatePostReportRequest | 201 PostReportResponse |
| MOD-02 | 없음 | 200 Page\[PostReportResponse\] |
| MOD-03 | 없음 | 200 PostReportResponse |
| MOD-04 | ReviewPostReportRequest | 200 PostReportResponse |

### 수거 분쟁·권한 제한

| ID | Method | Endpoint(Base URL 제외) | 기능 |
| --- | --- | --- | --- |
| ADS-01 | GET | <code>/admin/disputes</code> | 수거 분쟁 목록 |
| ADS-02 | GET | <code>/admin/disputes/{disputeId}</code> | 수거 분쟁 상세 |
| ADS-03 | POST | <code>/admin/disputes/{disputeId}/review</code> | 수거 분쟁 검토 |
| ADS-04 | PUT | <code>/admin/users/{userId}/collection-restriction</code> | 수거 권한 제한·해제 |

| ID | Request model | 성공 |
| --- | --- | --- |
| ADS-01 | 없음 | 200 Page\[AdminDisputeResponse\] |
| ADS-02 | 없음 | 200 AdminDisputeResponse |
| ADS-03 | ReviewDisputeRequest | 200 AdminDisputeResponse |
| ADS-04 | UpdateCollectionRestrictionRequest | 200 CollectionRestrictionResponse |

### 통계

| ID | Method | Endpoint(Base URL 제외) | 기능 |
| --- | --- | --- | --- |
| STA-01 | GET | <code>/admin/statistics</code> | 상태별 기본 통계 |

| ID | Request model | 성공 |
| --- | --- | --- |
| STA-01 | 없음 | 200 StatisticsResponse |

### 감사 로그

| ID | Method | Endpoint(Base URL 제외) | 기능 |
| --- | --- | --- | --- |
| AUD-01 | GET | <code>/admin/audit-logs</code> | 감사 로그 조회 |

| ID | Request model | 성공 |
| --- | --- | --- |
| AUD-01 | 없음 | 200 Page\[AuditLogResponse\] |

## ADM-01 권한 관리용 회원 조회

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/admin/users |
| 접근 | 관리자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 Page\[AdminUserSummary\] |
| 추가 실패 | 없음 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| query | page | integer | 아니오 | 기본0·최소0 |
| query | size | integer | 아니오 | 기본20·1\~100 |
| query | q | string | 아니오 | 가상 이름 부분검색,1\~100자 |
| query | role | MEMBER/ADMIN | 아니오 | 역할 필터 |

### Request model: 없음

본문 없음. 파라미터 외 입력 없음.

### 처리 규칙

1. 역할 부여 대상을 찾기 위한 최소 정보만 반환한다. 이메일·전화번호·mockSubject는 제외한다.
2. userId 오름차순 정렬한다. 수거 권한 제한 여부만 함께 표시한다.

### Response

```json
{
  "items": [
    {
      "userId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
      "name": "테스트 학생 1",
      "affiliation": "STUDENT",
      "role": "MEMBER",
      "collectionRestricted": false
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## ADM-02 관리자 권한 부여·회수

| 항목 | 내용 |
| --- | --- |
| Method / URL | PATCH /api/v1/admin/users/\{userId\}/role |
| 접근 | 관리자 |
| Request body | JSON |
| Request model | UpdateRoleRequest |
| 성공 | 200 AdminUserSummary |
| 추가 실패 | 409 LAST\_ADMIN |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 해당 세션 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| path | userId | UUID | 예 | 대상 리소스 식별자 |

### Request model: UpdateRoleRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| role | MEMBER/ADMIN | 예 | 부여할 최종 역할 |

```json
{
  "role": "ADMIN"
}
```

### 처리 규칙

1. ADMIN을 부여하거나 MEMBER로 변경하여 관리자 권한을 회수한다.
2. 요청한 역할과 같으면 200으로 현재 결과를 반환한다. 마지막 관리자 제거 방지(409 LAST\_ADMIN)는 운영 보호를 위한 제안이다.
3. 현재 DB 역할을 즉시 갱신해 기존 세션에도 적용하고 권한 변경을 감사 메타데이터에 남긴다. 다른 계정의 권한을 바꾸는 행위자 ID는 세션에서 결정한다.
4. 목업 재로그인 시에도 이 변경을 seed 역할로 덮어쓰지 않는다.

### Response

```json
{
  "userId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
  "name": "테스트 학생 1",
  "affiliation": "STUDENT",
  "role": "ADMIN",
  "collectionRestricted": false
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## REF-01 건물 전체 목록

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/admin/buildings |
| 접근 | 관리자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 Page\[BuildingResponse\] |
| 추가 실패 | 없음 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| query | page | integer | 아니오 | 기본0·최소0 |
| query | size | integer | 아니오 | 기본20·1\~100 |
| query | active | boolean | 아니오 | 미지정 시 활성·비활성 전부 |

### Request model: 없음

본문 없음. 파라미터 외 입력 없음.

### 처리 규칙

1. 비활성 건물까지 포함해 관리한다. 공개 목록과 구분한다.
2. code 오름차순 정렬한다.

### Response

```json
{
  "items": [
    {
      "buildingId": "ec91535b-2c67-4e78-877e-68c6c6c5faf2",
      "code": "E3",
      "nameKo": "전산학부",
      "nameEn": "School of Computing",
      "active": true
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## REF-02 건물 추가

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/admin/buildings |
| 접근 | 관리자 |
| Request body | JSON |
| Request model | CreateBuildingRequest |
| 성공 | 201 BuildingResponse |
| 추가 실패 | 409 BUILDING\_CODE\_EXISTS |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 해당 세션 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |

### Request model: CreateBuildingRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| code | string | 예 | 공백 제외1\~30자, 고유 건물 코드 |
| nameKo | string | 예 | 공백 제외1\~100자 |
| nameEn | string | 예 | 공백 제외1\~100자 |

```json
{
  "code": "E3",
  "nameKo": "전산학부",
  "nameEn": "School of Computing"
}
```

### 처리 규칙

1. 새 건물을 active=true로 생성한다. code는 앞뒤 공백 제거·대문자로 저장하고, DB에서도 lower(btrim(code)) 고유 인덱스로 중복을 검사한다. 이는 설계 제안의 구현 선택이다.
2. 이름은 한국어·영어 표시를 지원한다. 생성 행위자·시각을 기록한다.

### Response

```json
{
  "buildingId": "ec91535b-2c67-4e78-877e-68c6c6c5faf2",
  "code": "E3",
  "nameKo": "전산학부",
  "nameEn": "School of Computing",
  "active": true
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## REF-03 건물 이름 변경·비활성화

| 항목 | 내용 |
| --- | --- |
| Method / URL | PATCH /api/v1/admin/buildings/\{buildingId\} |
| 접근 | 관리자 |
| Request body | JSON |
| Request model | UpdateBuildingRequest |
| 성공 | 200 BuildingResponse |
| 추가 실패 | 없음 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 해당 세션 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| path | buildingId | UUID | 예 | 대상 리소스 식별자 |

### Request model: UpdateBuildingRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| nameKo | string | 아니오 | 공백 제외1\~100자 |
| nameEn | string | 아니오 | 공백 제외1\~100자 |
| active | boolean | 아니오 | false=비활성화, true=재활성화 제안 |

```json
{
  "active": false
}
```

### 처리 규칙

1. 이름 변경·비활성화를 지원하고 실제 삭제하지 않는다. 기존 게시물·분실 신고·보관 이력의 참조는 유지한다.
2. 비활성화된 건물은 신규 선택에서 제외하지만 기존 게시물 조회·검색의 과거 참조로 표시한다. 기존 수정에서 유지하는 경우에는 그대로 허용한다.
3. code와 buildingId는 변경할 수 없다. 최소1개 필드를 지정한다.

### Response

```json
{
  "buildingId": "ec91535b-2c67-4e78-877e-68c6c6c5faf2",
  "code": "E3",
  "nameKo": "전산학부",
  "nameEn": "School of Computing",
  "active": false
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## REF-04 카테고리 전체 목록

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/admin/categories |
| 접근 | 관리자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 Page\[CategoryResponse\] |
| 추가 실패 | 없음 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| query | page | integer | 아니오 | 기본0·최소0 |
| query | size | integer | 아니오 | 기본20·1\~100 |
| query | active | boolean | 아니오 | 미지정 시 전부 |

### Request model: 없음

본문 없음. 파라미터 외 입력 없음.

### 처리 규칙

1. 활성·비활성 카테고리와 민감 여부를 조회한다. categoryId 오름차순.

### Response

```json
{
  "items": [
    {
      "categoryId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
      "nameKo": "지갑",
      "nameEn": "Wallet",
      "active": true,
      "sensitive": true
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## REF-05 카테고리 추가

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/admin/categories |
| 접근 | 관리자 |
| Request body | JSON |
| Request model | CreateCategoryRequest |
| 성공 | 201 CategoryResponse |
| 추가 실패 | 409 CATEGORY\_NAME\_EXISTS |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 해당 세션 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |

### Request model: CreateCategoryRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| nameKo | string | 예 | 공백 제외1\~100자 |
| nameEn | string | 예 | 공백 제외1\~100자 |
| sensitive | boolean | 예 | 민감 물품 분류 여부 |

```json
{
  "nameKo": "지갑",
  "nameEn": "Wallet",
  "sensitive": true
}
```

### 처리 규칙

1. 카테고리를 active=true로 생성한다. 민감 분류 값은 서버의 접근 제어 근거이다. 이름은 앞뒤 공백을 제거하며 한국어·영어 각각 대소문자 무시 중복을 금지한다. 생성·이름 변경에 같은 규칙을 적용하는 구현 선택이다.
2. 민감 범주 예시는 신분증·지갑·휴대전화이며 최종 목록은 프로젝트 정책으로 확정해야 한다.
3. 민감 여부는 게시물 작성자가 임의로 지정할 수 없다.

### Response

```json
{
  "categoryId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
  "nameKo": "지갑",
  "nameEn": "Wallet",
  "active": true,
  "sensitive": true
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## REF-06 카테고리 이름 변경·비활성화

| 항목 | 내용 |
| --- | --- |
| Method / URL | PATCH /api/v1/admin/categories/\{categoryId\} |
| 접근 | 관리자 |
| Request body | JSON |
| Request model | UpdateCategoryRequest |
| 성공 | 200 CategoryResponse |
| 추가 실패 | 409 CATEGORY\_NAME\_EXISTS |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 해당 세션 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| path | categoryId | UUID | 예 | 대상 리소스 식별자 |

### Request model: UpdateCategoryRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| nameKo | string | 아니오 | 공백 제외1\~100자 |
| nameEn | string | 아니오 | 공백 제외1\~100자 |
| active | boolean | 아니오 | false=비활성화, true=재활성화 제안 |

```json
{
  "nameKo": "지갑·카드지갑"
}
```

### 처리 규칙

1. 이름 변경·비활성화만 수행하고 기존 자료의 참조를 유지한다.
2. 비활성 카테고리도 과거 게시물은 조회 가능하다. 새로운 게시물·신고 선택에서는 제외한다.
3. sensitive와 categoryId는 이 API에서 변경하지 않는다. 민감 등급 변경과 기존 파일 재분류는 별도 검토가 필요한 설계 범위이다.

### Response

```json
{
  "categoryId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
  "nameKo": "지갑·카드지갑",
  "nameEn": "Wallet",
  "active": true,
  "sensitive": true
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## MOD-01 부적절한 게시물 신고

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/found-items/\{itemId\}/reports |
| 접근 | 로그인 회원·관리자 |
| Request body | JSON |
| Request model | CreatePostReportRequest |
| 성공 | 201 PostReportResponse |
| 추가 실패 | 409 OPEN\_REPORT\_EXISTS |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 해당 세션 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| path | itemId | UUID | 예 | 대상 리소스 식별자 |

### Request model: CreatePostReportRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| reasonCode | INAPPROPRIATE/SPAM/OTHER | 예 | 신고 사유 분류, 설계 제안 |
| details | string | 예 | 공백 제외1\~1000자, 추가 개인정보 입력 금지 |

```json
{
  "reasonCode": "INAPPROPRIATE",
  "details": "물품과 무관한 게시물입니다."
}
```

### 처리 규칙

1. 비회원 신고는 401. 회원이 부적절한 게시물을 신고한다.
2. 회원의 신고만으로 숨기지 않고 관리자 검토를 기다린다.
3. 현재 사용자와 itemId의 OPEN 신고 중복은 409로 방지하는 제안이다. 게시물 상태 POSTED/COLLECTED/EXPIRED와 신고 가능 여부를 구분한다.

### Response

```json
{
  "reportId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd",
  "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
  "reporterId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
  "reasonCode": "INAPPROPRIATE",
  "details": "물품과 무관한 게시물입니다.",
  "status": "OPEN",
  "createdAt": "2026-11-02T16:00:00+09:00",
  "decision": null,
  "reviewedAt": null,
  "reviewerId": null
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## MOD-02 게시물 신고 목록

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/admin/post-reports |
| 접근 | 관리자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 Page\[PostReportResponse\] |
| 추가 실패 | 없음 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| query | page | integer | 아니오 | 기본0·최소0 |
| query | size | integer | 아니오 | 기본20·1\~100 |
| query | status | OPEN/REVIEWED | 아니오 | 미지정 시 전부 |
| query | itemId | UUID | 아니오 | 물품 필터 |

### Request model: 없음

본문 없음. 파라미터 외 입력 없음.

### 처리 규칙

1. createdAt 내림차순으로 신고를 반환한다.
2. 연락처·민감 사진·보관 위치·분실 신고 private details를 포함하지 않는다. 민감 자료는 기존 권한·감사 전용 조회 API로만 접근한다.

### Response

```json
{
  "items": [
    {
      "reportId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd",
      "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
      "reporterId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
      "reasonCode": "INAPPROPRIATE",
      "details": "물품과 무관한 게시물입니다.",
      "status": "OPEN",
      "createdAt": "2026-11-02T16:00:00+09:00",
      "decision": null,
      "reviewedAt": null,
      "reviewerId": null
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## MOD-03 게시물 신고 상세

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/admin/post-reports/\{reportId\} |
| 접근 | 관리자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 PostReportResponse |
| 추가 실패 | 없음 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| path | reportId | UUID | 예 | 대상 리소스 식별자 |

### Request model: 없음

본문 없음. 파라미터 외 입력 없음.

### 처리 규칙

1. 신고 메타데이터를 제공한다. 관리자라는 이유로 신고 응답에 민감 사진이나 보관 위치를 끼워 넣지 않는다.

### Response

```json
{
  "reportId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd",
  "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
  "reporterId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
  "reasonCode": "INAPPROPRIATE",
  "details": "물품과 무관한 게시물입니다.",
  "status": "OPEN",
  "createdAt": "2026-11-02T16:00:00+09:00",
  "decision": null,
  "reviewedAt": null,
  "reviewerId": null
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## MOD-04 신고 검토·숨김

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/admin/post-reports/\{reportId\}/review |
| 접근 | 관리자 |
| Request body | JSON |
| Request model | ReviewPostReportRequest |
| 성공 | 200 PostReportResponse |
| 추가 실패 | 409 REPORT\_ALREADY\_REVIEWED |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 해당 세션 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| path | reportId | UUID | 예 | 대상 리소스 식별자 |

### Request model: ReviewPostReportRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| decision | HIDE/DISMISS | 예 | 게시물 숨김 또는 신고 기각 |

```json
{
  "decision": "HIDE"
}
```

### 처리 규칙

1. HIDE는 연결된 게시물 hidden=true로 변경하고 신고를 REVIEWED 처리한다. DISMISS는 신고만 검토 완료로 처리한다.
2. 게시물은 어떤 상태라도 숨길 수 있다. POSTED/COLLECTED/EXPIRED 자체는 변경하지 않는다.
3. 숨긴 게시물은 비회원·일반 회원 공개 목록·직접 상세·매칭 미리보기·사진 링크 발급에서 제외한다. 작성자의 관리 화면과 관리자만 계속 접근한다.
4. 숨김만으로 수거·만료 종료 처리나 메시지 삭제를 하지 않는다. 이미 발급된 사진 링크의 처리는 사진 명세의 접근 재검사 규칙을 따른다.
5. 이미 REVIEWED이면 409. 검토자·시각·결과 및 숨김 변경은 함께 기록한다. 숨김 해제는 SRS에 없어 이번 초안에 별도 API를 추가하지 않는다.

### Response

```json
{
  "reportId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd",
  "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
  "reporterId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
  "reasonCode": "INAPPROPRIATE",
  "details": "물품과 무관한 게시물입니다.",
  "status": "REVIEWED",
  "createdAt": "2026-11-02T16:00:00+09:00",
  "decision": "HIDE",
  "reviewedAt": "2026-11-02T16:30:00+09:00",
  "reviewerId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed"
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## ADS-01 수거 분쟁 목록

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/admin/disputes |
| 접근 | 관리자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 Page\[AdminDisputeResponse\] |
| 추가 실패 | 없음 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| query | page | integer | 아니오 | 기본0·최소0 |
| query | size | integer | 아니오 | 기본20·1\~100 |
| query | status | OPEN/RESOLVED | 아니오 | 기본 OPEN |
| query | itemId | UUID | 아니오 | 물품 필터 |

### Request model: 없음

본문 없음. 파라미터 외 입력 없음.

### 처리 규칙

1. createdAt 내림차순으로 수거 분쟁을 조회한다.
2. 검토에 필요한 행위자 ID와 분쟁·수거 메타데이터만 제공한다. 메시지 본문과 연락처는 제외한다.

### Response

```json
{
  "items": [
    {
      "disputeId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd",
      "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
      "collectionId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
      "finderId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
      "collectorId": "c30cfe55-eac5-48ac-83c6-aefef64018c1",
      "reason": "잘못된 수거 표시입니다.",
      "status": "OPEN",
      "decision": null,
      "createdAt": "2026-11-02T16:00:00+09:00",
      "resolvedAt": null
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## ADS-02 수거 분쟁 상세

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/admin/disputes/\{disputeId\} |
| 접근 | 관리자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 AdminDisputeResponse |
| 추가 실패 | 없음 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| path | disputeId | UUID | 예 | 대상 리소스 식별자 |

### Request model: 없음

본문 없음. 파라미터 외 입력 없음.

### 처리 규칙

1. 수거 기록·감사 로그를 연결하여 검토한다. 종료 시 삭제된 메시지를 복원하거나 백업에서 열람하지 않는다.
2. 민감 사진·보관 위치의 원문을 포함하지 않는다. 별도 민감 자료 API를 이용하면 해당 열람도 FR-30에 따라 기록한다.

### Response

```json
{
  "disputeId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd",
  "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
  "collectionId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
  "finderId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
  "collectorId": "c30cfe55-eac5-48ac-83c6-aefef64018c1",
  "reason": "잘못된 수거 표시입니다.",
  "status": "OPEN",
  "decision": null,
  "createdAt": "2026-11-02T16:00:00+09:00",
  "resolvedAt": null
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## ADS-03 수거 분쟁 검토

| 항목 | 내용 |
| --- | --- |
| Method / URL | POST /api/v1/admin/disputes/\{disputeId\}/review |
| 접근 | 관리자 |
| Request body | JSON |
| Request model | ReviewDisputeRequest |
| 성공 | 200 AdminDisputeResponse |
| 추가 실패 | 400 INVALID\_DECISION, 409 DISPUTE\_ALREADY\_RESOLVED |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 해당 세션 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| path | disputeId | UUID | 예 | 대상 리소스 식별자 |

### Request model: ReviewDisputeRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| decision | UPHELD/DISMISSED | 예 | 분쟁 인용·기각. 제안 enum |
| blockCollector | boolean | 예 | 인용 시 수거 권한 제한 여부, 기각 시 false만 허용 |

```json
{
  "decision": "UPHELD",
  "blockCollector": true
}
```

### 처리 규칙

1. OPEN 분쟁만 검토한다. decision과 resolvedAt, 검토자 ID를 저장한다.
2. UPHELD와 blockCollector=true일 때 해당 분쟁의 수거자에게 수거 표시 제한을 적용한다. 게시물 등록·메시지 등 다른 회원 기능을 막지 않는다.
3. 분쟁 검토 자체는 수거를 자동 취소하지 않는다. 잘못된 표시를 되돌리려면 관리자도 허용되는 DELETE /found-items/\{itemId\}/collection을 명시적으로 호출한다.
4. 수거 표시가 이미 취소되었어도 과거 분쟁은 검토할 수 있다. 이후 새 수거 기록이나 다른 사람에게 잘못 제한을 적용하지 않도록 분쟁의 collectionId를 기준으로 한다.
5. 원자적으로 검토·제한·감사 메타데이터를 기록한다. 메시지는 보존하지 않는다.

### Response

```json
{
  "disputeId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd",
  "itemId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
  "collectionId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882",
  "finderId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
  "collectorId": "c30cfe55-eac5-48ac-83c6-aefef64018c1",
  "reason": "잘못된 수거 표시입니다.",
  "status": "RESOLVED",
  "decision": "UPHELD",
  "createdAt": "2026-11-02T16:00:00+09:00",
  "resolvedAt": "2026-11-02T17:00:00+09:00"
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## ADS-04 수거 권한 제한·해제

| 항목 | 내용 |
| --- | --- |
| Method / URL | PUT /api/v1/admin/users/\{userId\}/collection-restriction |
| 접근 | 관리자 |
| Request body | JSON |
| Request model | UpdateCollectionRestrictionRequest |
| 성공 | 200 CollectionRestrictionResponse |
| 추가 실패 | 409 DISPUTE\_NOT\_UPHELD / COLLECTOR\_MISMATCH |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 해당 세션 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| path | userId | UUID | 예 | 대상 리소스 식별자 |

### Request model: UpdateCollectionRestrictionRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| restricted | boolean | 예 | true 제한, false 해제 |
| disputeId | UUID | 조건부 | restricted=true이면 필수. 해당 회원의 인용된 분쟁. 해제 시 생략 가능하며 명시적 null은 거부 |

```json
{
  "restricted": true,
  "disputeId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd"
}
```

### 처리 규칙

1. restricted=true는 disputeId가 필수다. 검토 완료·인용된 분쟁인지와 대상 회원이 해당 수거 기록의 수거자인지 검사한다. 불일치 시 각각 DISPUTE_NOT_UPHELD / COLLECTOR_MISMATCH를 반환한다. 존재하지 않는 회원·분쟁은 404 NOT_FOUND다.
2. restricted=false는 관리자만 실행하며 disputeId를 생략할 수 있다. 기존 제한 상태를 기준으로 해제하므로 근거 분쟁이 보존 만료로 삭제되어도 해제할 수 있다. disputeId를 제공하면 설정과 동일한 분쟁·수거자 검증을 수행한다. 생략하면 기존 source_dispute_id를 유지하며 삭제된 근거를 복원하지 않는다.
3. 같은 상태 요청은 200이다. 제한 행이 없는 회원의 해제 요청도 restricted=false인 상태 행을 생성해 응답한다. 회원 역할이나 로그인 가능 여부는 변경하지 않는다.
4. 근거 분쟁 삭제 시 source_dispute_id만 NULL로 바꾸고 제한 상태는 유지한다. 분쟁 삭제 자체로 자동 해제하지 않으며, 해제를 위해 분쟁·수거 기록의 보존기간을 연장하지 않는다.
5. 상태 변경과 감사 기록은 같은 트랜잭션으로 처리한다. 행위자 ADMIN·대상 USER·시각과 restricted를 기록하고, 유효한 근거 분쟁 ID가 남아 있을 때만 metadata.disputeId를 포함한다. 별도 자유서술 개인정보나 삭제된 분쟁 원문을 수집·복원하지 않는다.
6. 명시적 해제까지 기한 없이 유지하는 정책과 위 해제 절차는 SRS 미정 사항을 보완한 설계 제안이다. SRS의 기존 확정 요구사항으로 간주하지 않는다.

근거 분쟁 삭제 후 해제 요청 예시:

```json
{
  "restricted": false
}
```

### Response

```json
{
  "userId": "c30cfe55-eac5-48ac-83c6-aefef64018c1",
  "restricted": true,
  "disputeId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd",
  "updatedAt": "2026-11-02T17:00:00+09:00"
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## STA-01 상태별 기본 통계

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/admin/statistics |
| 접근 | 관리자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 StatisticsResponse |
| 추가 실패 | 없음 |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |

### Request model: 없음

본문 없음. 파라미터 외 입력 없음.

### 처리 규칙

1. 현재 보존 중인 삭제되지 않은 습득물의 상태별 개수를 반환한다. POSTED/COLLECTED/EXPIRED 각각을 집계한다.
2. 숨김 여부는 상태와 별개이므로 숨긴 게시물도 집계한다. 통계에 숨김 배제 필터를 암묵적으로 적용하지 않는다.
3. 보존기간 후 삭제한 개인 식별 기록을 통계 때문에 계속 보존하지 않는다. 따라서 이 수치는 영구 누적 건수가 아니다.
4. 기간별 통계는 SRS 필수가 아니므로 이 초안에는 기간 파라미터를 추가하지 않는다.

### Response

```json
{
  "postedCount": 12,
  "collectedCount": 5,
  "expiredCount": 3,
  "asOf": "2026-11-02T17:00:00+09:00"
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## AUD-01 감사 로그 조회

| 항목 | 내용 |
| --- | --- |
| Method / URL | GET /api/v1/admin/audit-logs |
| 접근 | 관리자 |
| Request body | 없음 |
| Request model | 없음 |
| 성공 | 200 Page\[AuditLogResponse\] |
| 추가 실패 | 400 INVALID\_TIME\_RANGE |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 현재 로그인 세션 |
| header | Accept-Language | ko/en | 아니오 | 기본 ko |
| query | page | integer | 아니오 | 기본0·최소0 |
| query | size | integer | 아니오 | 기본20·1\~100 |
| query | actorId | UUID | 아니오 | 행위자 필터 |
| query | targetId | UUID | 아니오 | 대상 필터 |
| query | action | AuditAction | 아니오 | 아래 enum |
| query | from | date-time | 아니오 | 이 시각 이상 |
| query | to | date-time | 아니오 | 이 시각 미만. from보다 뒤 |

### Request model: 없음

본문 없음. 파라미터 외 입력 없음.

### 처리 규칙

1. occurredAt 내림차순. 관리자가 읽기만 가능하며 일반 사용자용 로그 작성·수정·삭제 API는 없다.
2. FR-30 필수 이벤트인 상태 변경·수거 표시·위치 변경·민감 사진/보관 위치 열람을 빠짐없이 기록한다. 서버 배치 작업은 actorType=SYSTEM, actorId=null로 기록한다.
3. 감사 레코드는 행위자·대상·행위·시각과 최소 식별 메타데이터만 저장한다. 사진 원문/URL, 보관 위치 원문, 메시지 본문, 분실 신고 private details, 이메일·전화번호·IP는 저장하지 않는다.
4. 감사 기록 실패 시 해당 변경·민감 열람을 성공시키지 않거나 신뢰성 있는 원자적 로그 예약으로 누락을 방지한다.
5. 각 로그는 생성 시각부터 1년 후 삭제한다. 개인정보 삭제 후 감사 로그에서 원문을 복원할 수 없어야 한다.

### Response

```json
{
  "items": [
    {
      "auditLogId": "cefb82f5-85ae-4e3a-ae09-c0d71c5585dd",
      "actorId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed",
      "actorType": "MEMBER",
      "action": "COLLECTION_MARKED",
      "targetType": "FOUND_ITEM",
      "targetId": "4fb27e56-48a8-4786-8ac5-56db202a0020",
      "occurredAt": "2026-11-02T16:00:00+09:00",
      "metadata": {
        "fromStatus": "POSTED",
        "toStatus": "COLLECTED",
        "collectionId": "ddba082c-1589-4bc7-b82e-fbc9d42ac882"
      }
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

전체 응답 필드는 아래 공통 Response Model에 정의한다.

## 공통 Response Model

| 모델 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| AdminUserSummary | userId | UUID | 예 | 사용자 ID |
| AdminUserSummary | name | string | 예 | SSO 또는 가상 이름 |
| AdminUserSummary | affiliation | STUDENT/FACULTY/STAFF | 예 | 소속 |
| AdminUserSummary | role | MEMBER/ADMIN | 예 | 현재 역할 |
| AdminUserSummary | collectionRestricted | boolean | 예 | 수거 표시 제한 |
| BuildingResponse | buildingId | UUID | 예 | 건물 ID |
| BuildingResponse | code | string | 예 | 고유 코드 |
| BuildingResponse | nameKo / nameEn | string 각각 | 예 | 이름 |
| BuildingResponse | active | boolean | 예 | 신규 선택 가능 여부 |
| CategoryResponse | categoryId | UUID | 예 | 카테고리 ID |
| CategoryResponse | nameKo / nameEn | string 각각 | 예 | 이름 |
| CategoryResponse | active / sensitive | boolean 각각 | 예 | 활성·민감 여부 |
| PostReportResponse | reportId / itemId / reporterId | UUID 각각 | 예 | 신고·물품·신고자 |
| PostReportResponse | reasonCode | INAPPROPRIATE/SPAM/OTHER | 예 | 사유 |
| PostReportResponse | details | string | 예 | 설명 |
| PostReportResponse | status | OPEN/REVIEWED | 예 | 처리상태 |
| PostReportResponse | createdAt | date-time | 예 | 신고시각 |
| PostReportResponse | decision | HIDE/DISMISS/null | 예 | 처리결과 |
| PostReportResponse | reviewedAt | date-time/null | 예 | 검토시각 |
| PostReportResponse | reviewerId | UUID/null | 예 | 검토자 |
| AdminDisputeResponse | disputeId / itemId / collectionId / finderId / collectorId | UUID 각각 | 예 | 분쟁·물품·수거·관련 회원 ID |
| AdminDisputeResponse | reason | string | 예 | 분쟁사유 |
| AdminDisputeResponse | status | OPEN/RESOLVED | 예 | 분쟁상태 |
| AdminDisputeResponse | decision | UPHELD/DISMISSED/null | 예 | 인용·기각 |
| AdminDisputeResponse | createdAt / resolvedAt | date-time, date-time/null | 예 | 접수·해결 시각 |
| CollectionRestrictionResponse | userId | UUID | 예 | 회원 |
| CollectionRestrictionResponse | disputeId | UUID/null | 예 | 저장된 근거 분쟁. 근거 삭제 또는 근거 없이 해제 상태를 생성한 경우 null |
| CollectionRestrictionResponse | restricted | boolean | 예 | 제한 여부 |
| CollectionRestrictionResponse | updatedAt | date-time | 예 | 변경 시각 |
| StatisticsResponse | postedCount / collectedCount / expiredCount | integer 각각 | 예 | 0 이상 상태별 수 |
| StatisticsResponse | asOf | date-time | 예 | 집계 시각 |
| AuditLogResponse | auditLogId | UUID | 예 | 로그 ID |
| AuditLogResponse | actorId | UUID/null | 예 | 회원 또는 null(SYSTEM) |
| AuditLogResponse | actorType | MEMBER/ADMIN/SYSTEM | 예 | 행위 주체 |
| AuditLogResponse | action | AuditAction | 예 | 행위 |
| AuditLogResponse | targetType | FOUND\_ITEM/LOST\_REPORT/COLLECTION/USER/BUILDING/CATEGORY/POST\_REPORT/DISPUTE | 예 | 대상 종류 |
| AuditLogResponse | targetId | UUID | 예 | 대상 ID |
| AuditLogResponse | occurredAt | date-time | 예 | 발생 시각 |
| AuditLogResponse | metadata | object | 예 | 허용목록 필드만. 아래 정의 |

AuditAction 필수값: ITEM\_STATUS\_CHANGED, COLLECTION\_MARKED, COLLECTION\_UNDONE, DROP\_OFF\_CHANGED, SENSITIVE\_PHOTO\_VIEWED, SENSITIVE\_DROP\_OFF\_VIEWED. 분실 신고 생성·수동 해결·자동 종료·수거에 따른 종료 등 모든 상태 전이는 LOST\_REPORT\_STATUS\_CHANGED로 기록한다. PHOTO\_ACCESS\_URL\_ISSUED는 사진 URL 발급을 추적하는 추가 이벤트이며 실제 민감 사진 열람 이벤트 SENSITIVE\_PHOTO\_VIEWED를 대체하지 않는다. 추가 운영값 제안: ROLE\_CHANGED, REFERENCE\_CREATED, REFERENCE\_UPDATED, POST\_HIDDEN, POST\_REPORT\_REVIEWED, DISPUTE\_REVIEWED, COLLECTION\_RESTRICTION\_CHANGED.

운영 명령으로 실패 분석을 수동 재시도하면 SYSTEM/TEXT_ANALYSIS_RETRIED를 기록한다. 대상은 FOUND_ITEM 또는 LOST_REPORT이며 metadata에는 eventId(UUID)만 기록한다. 이 액션도 기존 감사 목록·action 필터에서 조회할 수 있다. 회원용 재시도 엔드포인트는 추가하지 않는다.

실패한 generation 재평가를 수동 재시도하면 SYSTEM/MATCH_EVALUATION_RETRIED를 기록한다. 대상은 FOUND_ITEM 또는 LOST_REPORT, metadata.eventId는 재평가 작업 UUID다. 기존 감사 목록·action 필터를 사용하며 새로운 HTTP 엔드포인트는 없다. 감사 action 허용 목록은 revision 20261108_0008부터 적용된다.

metadata 허용필드: fromStatus/toStatus(대상별 POSTED/COLLECTED/EXPIRED 또는 OPEN/RESOLVED/CLOSED), collectionId/photoId/reportId/disputeId/eventId(UUID), fromRole/toRole(MEMBER/ADMIN), restricted(boolean), decision(위 enum). 값이 없으면 키 생략. 위치 변경은 위치 원문 대신 targetId·행위·시각으로 추적한다. 카테고리·건물 이름이나 신고 사유 원문을 로그 metadata에 복제하지 않는다.

## 보존·검증 기준

| 요구사항 | 검증 |
| --- | --- |
| FR-3 | 관리자만 역할 부여·회수, 변경 즉시 세션 권한 반영 |
| FR-27 | 건물·카테고리 추가·이름 변경·비활성화. 기존 참조 삭제 없음 |
| FR-28 | 3개 상태별 수 반환. 숨김과 상태를 분리 |
| FR-29 | 회원 신고→관리자 검토→숨김. 신고 자체로 자동 숨김 금지 |
| FR-23 | 분쟁 검토, 수거 표시 권한만 제한. 다른 기능 유지 |
| FR-30 | 필수 이벤트마다 who/what/when, 1년 보존. 민감 열람 우회 경로 없음 |
| SEC-3·SEC-5 | 연락처·메시지·private details를 관리자 목록·감사 메타데이터에 복제하지 않음 |
| 3.3 | 기준정보는 참조 유지. 신고·분쟁 메타데이터는 물품 종료 후1년 또는 연결 수거 기록1년 범위에서 정리하는 설계 제안. 별도 영구 개인정보 보관 없음 |

SRS 미정: 수거 제한 기간·해제 기준, 민감 카테고리 최종 목록, 추가 메시지 분쟁 보존 여부. 현재 초안은 메시지 종료즉시삭제를 유지한다. 운영 보호 제안인 마지막 관리자 제거 방지·신고 중복 제한·수거 제한 해제는 SRS의 기존 확정 요구사항으로 간주하지 않는다.

