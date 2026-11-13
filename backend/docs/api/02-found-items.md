# 습득물·검색·사진

> 원문: [Notion](https://app.notion.com/p/40c23542cf8c81eba6ebeb28c8f9d084?pvs=204) · 내보낸 날짜: 2026-11-02 (KST)

## 범위·공통 계약

SRS 전체를 읽고 FR-5\~9, FR-13\~15, FR-25\~26과 SI-3·SEC-2/4·FR-30을 구체화했다. Must: FR-5/6/7/13/14/25. Should: FR-8/9/26. Could: FR-15. 경로·DTO·제한값은 설계 초안이며 구현 완료를 뜻하지 않는다.

인증은 [인증](01-auth.md), 공통 형식은 [공통 규칙·운영 요구사항](00-common.md)을 따른다.

### 요청·응답 형식

| 항목 | 규칙 |
| --- | --- |
| 기본 | /api/v1, JSON. UUID ID, RFC3339 KST +09:00, 날짜 YYYY-MM-DD |
| 캐시 | 위치·이력·사진 URL·바이트 및 역할별 조회 응답 Cache-Control: private, no-store. CDN·서비스워커 캐시 금지 |
| 언어 | 선택 header Accept-Language ko/en 기본 ko. 오류 code는 고정, message만 번역 |

### 인증·권한·적용 범위

| 항목 | 규칙 |
| --- | --- |
| 인증 | KAIFIND\_SESSION, 쓰기 X-CSRF-Token. ADMIN도 타인 작성자 수정·삭제 자동 허용 아님 |
| 상태 | POSTED/COLLECTED/EXPIRED. hidden은 별개. status·hidden은 일반 수정 불가 |

### 개인정보·접근 제어

| 항목 | 규칙 |
| --- | --- |
| 비공개 | 모든 보관 위치·사진·과거 이력은 회원 전용. 민감 물품사진 metadata·altText·바이트는 비회원 비공개 |
| 개인정보 | 공개 응답에 이메일·전화번호·SSO 식별자 없음 |
| 민감 판정 | category.sensitive. 민감 분류의 하향 변경 API 없음. 과거 보호사진을 잘못 공개하지 않도록 연결 시 보호 라벨 유지 |
| 감사 | 민감사진·현재/과거 위치의 실제 열람마다 회원·대상·행위·시각 기록. 감사 저장 실패 시 데이터 미전달 |
| 이미지 | 물품사진·보관사진 모두 altText 필수. 자동 이미지 인식 없음 |

### 목록·페이지네이션

| 항목 | 규칙 |
| --- | --- |
| 페이지 | items,page,size,totalElements,totalPages 최상위. page=0 size=20 max100 |

### 오류 처리

| 항목 | 규칙 |
| --- | --- |
| HTTP 400 | <code>VALIDATION_ERROR/MALFORMED_JSON</code> |
| HTTP 401 | <code>AUTH_REQUIRED/SESSION_EXPIRED</code> |
| HTTP 403 | <code>FORBIDDEN/CSRF_INVALID/ORIGIN_NOT_ALLOWED</code> |
| HTTP 404 | <code>NOT_FOUND</code> |
| HTTP 409 | <code>STATE_CONFLICT</code> |
| HTTP 415 | <code>UNSUPPORTED_MEDIA_TYPE</code> |
| HTTP 500 | <code>INTERNAL_SERVER_ERROR</code> |

## 1. 엔드포인트 목록

### 습득물·검색·보관 위치

| ID | Method | Endpoint (/api/v1 생략) | 기능 |
| --- | --- | --- | --- |
| ITEM-01 | GET | <code>/found-items</code> | 검색·목록 |
| ITEM-02 | GET | <code>/found-items/{itemId}</code> | 공개 상세 |
| ITEM-03 | POST | <code>/found-items</code> | 습득물 등록 |
| ITEM-04 | PATCH | <code>/found-items/{itemId}</code> | 자기 게시물 수정 |
| ITEM-05 | DELETE | <code>/found-items/{itemId}</code> | 자기 게시물 삭제 |
| ITEM-06 | GET | <code>/found-items/{itemId}/drop-off</code> | 보관 위치 조회 |
| ITEM-07 | PUT | <code>/found-items/{itemId}/drop-off</code> | 보관 위치 변경 |
| ITEM-08 | GET | <code>/found-items/{itemId}/drop-off/history</code> | 보관 위치 이력 |
| ITEM-09 | POST | <code>/found-items/{itemId}/repost</code> | 만료 재등록 |
| ITEM-10 | GET | <code>/me/found-items</code> | 내 게시물 |

| ID | 접근 | Request model | Response model |
| --- | --- | --- | --- |
| ITEM-01 | 모두 | 없음 | FoundItemPage |
| ITEM-02 | 모두 | 없음 | FoundItemDetail |
| ITEM-03 | 회원 | CreateFoundItemRequest | FoundItemDetail |
| ITEM-04 | 작성자 | UpdateFoundItemRequest | FoundItemDetail |
| ITEM-05 | 작성자 | 없음 | 없음 |
| ITEM-06 | 회원 | 없음 | DropOffResponse |
| ITEM-07 | 작성자 | DropOffInput | DropOffResponse |
| ITEM-08 | 회원 | 없음 | DropOffHistoryPage |
| ITEM-09 | 작성자 | 없음 | FoundItemDetail |
| ITEM-10 | 회원 | 없음 | FoundItemPage |

### 사진

| ID | Method | Endpoint (/api/v1 생략) | 기능 |
| --- | --- | --- | --- |
| PHOTO-01 | POST | <code>/photos</code> | 사진 업로드 |
| PHOTO-02 | POST | <code>/photos/{photoId}/access-url</code> | 사진 단기 링크 |
| PHOTO-03 | GET | <code>/photo-access/{accessToken}</code> | 사진 바이트 |

| ID | 접근 | Request model | Response model |
| --- | --- | --- | --- |
| PHOTO-01 | 회원 | PhotoUploadRequest | PhotoUploadResponse |
| PHOTO-02 | 조건부 | 없음 | PhotoAccessResponse |
| PHOTO-03 | 조건부 | 없음 | binary image |

### 공개 기준정보

| ID | Method | Endpoint (/api/v1 생략) | 기능 |
| --- | --- | --- | --- |
| REF-01 | GET | <code>/buildings</code> | 활성 건물 목록·집계 |
| REF-02 | GET | <code>/categories</code> | 활성 카테고리 |

| ID | 접근 | Request model | Response model |
| --- | --- | --- | --- |
| REF-01 | 모두 | 없음 | BuildingListResponse |
| REF-02 | 모두 | 없음 | CategoryListResponse |

## ITEM-01. 검색·목록

| 항목 | 명세 |
| --- | --- |
| Method / URL | GET /api/v1/found-items |
| 접근 | 모두 |
| Request body | 없음. \{\}도 불필요 |
| Request model | 없음 |
| Response | 200 FoundItemPage |
| 오류 | 공통 오류 |
| 처리 | createdAt 내림차순·동률 itemId 내림차순. statuses 생략 시 POSTED만. hidden/deleted 제외. 검색 인덱스는 제목·설명만 사용하고 보관 위치·연락처는 넣지 않음. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| query | q | string | 아니오 | 1\~100자, 제목·설명 키워드 |
| query | categoryId | UUID | 아니오 | 카테고리 |
| query | foundBuildingId | UUID | 아니오 | 발견 건물. 보관 건물 아님 |
| query | foundDateFrom | date | 아니오 | KST 발견일 시작 포함 |
| query | foundDateTo | date | 아니오 | KST 발견일 종료 포함, 시작\<=종료 |
| query | statuses | ItemStatus\[\] | 아니오 | 반복 쿼리 statuses=POSTED&statuses=EXPIRED, enum만 |
| query | page | integer | 아니오 | 0 이상 기본0 |
| query | size | integer | 아니오 | 1\~100 기본20 |

## ITEM-02. 공개 상세

| 항목 | 명세 |
| --- | --- |
| Method / URL | GET /api/v1/found-items/\{itemId\} |
| 접근 | 모두 |
| Request body | 없음. \{\}도 불필요 |
| Request model | 없음 |
| Response | 200 FoundItemDetail |
| 오류 | 공통 오류 |
| 처리 | 보관 위치·사진은 항상 별도 조회. 민감사진 metadata·altText도 비회원 제외. hidden은 작성자·관리자만 조회하고 다른 사용자는 404. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 아니오 | 로그인 시 회원 사진 metadata·작성자/관리자 hidden 조회 권한 적용 |
| path | itemId | UUID | 예 | 대상 ID |

## ITEM-03. 습득물 등록

| 항목 | 명세 |
| --- | --- |
| Method / URL | POST /api/v1/found-items |
| 접근 | 회원 |
| Request body | JSON |
| Request model | CreateFoundItemRequest |
| Response | 201 FoundItemDetail |
| 오류 | 공통 오류, 409 PHOTO\_ALREADY\_ATTACHED / 400 INVALID\_REFERENCE |
| 처리 | 초기 POSTED. 본인 업로드 사진만 연결, 물품 사진 최소 1장. 매칭 재평가·신규 후보 알림 작업 등록. Location=/api/v1/found-items/\{itemId\}. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 로그인 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |

## ITEM-04. 자기 게시물 수정

| 항목 | 명세 |
| --- | --- |
| Method / URL | PATCH /api/v1/found-items/\{itemId\} |
| 접근 | 작성자 |
| Request body | JSON |
| Request model | UpdateFoundItemRequest |
| Response | 200 FoundItemDetail |
| 오류 | 공통 오류, 409 PHOTO\_ALREADY\_ATTACHED / 400 INVALID\_REFERENCE |
| 처리 | 전체 상태에서 본인 수정 가능. status/hidden/보관 위치는 변경 불가. 수정 후 전체 필수조건 검증·매칭 재평가. 기존 비활성 참조 유지 허용, 비활성값으로 새 변경 불가. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 로그인 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| path | itemId | UUID | 예 | 대상 ID |

## ITEM-05. 자기 게시물 삭제

| 항목 | 명세 |
| --- | --- |
| Method / URL | DELETE /api/v1/found-items/\{itemId\} |
| 접근 | 작성자 |
| Request body | 없음. \{\}도 불필요 |
| Request model | 없음 |
| Response | 204 없음 |
| 오류 | 공통 오류 |
| 처리 | 즉시 검색·조회 제외하고 deletedAt을 기록하는 논리 삭제. 후보·메시지는 즉시 삭제. 물품·사진·위치 이력은 비공개 보존 후 1년 만료 시 물리 삭제하며 별도 수거 기록·감사 로그도 1년 보존. 기존 상태는 유지하고 삭제를 새 물품 상태로 추가하지 않음. 미종료 물품 삭제의 보존 기산점은 deletedAt으로 제안. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 로그인 세션의 CSRF 토큰 |
| path | itemId | UUID | 예 | 대상 ID |

## ITEM-06. 보관 위치 조회

| 항목 | 명세 |
| --- | --- |
| Method / URL | GET /api/v1/found-items/\{itemId\}/drop-off |
| 접근 | 회원 |
| Request body | 없음. \{\}도 불필요 |
| Request model | 없음 |
| Response | 200 DropOffResponse |
| 오류 | 공통 오류 |
| 처리 | 민감 물품이면 매 조회 회원·대상·시각 감사 기록. 직접 보관이면 실제 위치 없음, 물품별 메시지로 연락. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효 로그인 세션 |
| path | itemId | UUID | 예 | 대상 ID |

## ITEM-07. 보관 위치 변경

| 항목 | 명세 |
| --- | --- |
| Method / URL | PUT /api/v1/found-items/\{itemId\}/drop-off |
| 접근 | 작성자 |
| Request body | JSON |
| Request model | DropOffInput |
| Response | 200 DropOffResponse |
| 오류 | 공통 오류, 409 PHOTO\_ALREADY\_ATTACHED / 400 INVALID\_REFERENCE |
| 처리 | 이전·이후 위치 이력·행위자·시각 기록. 발견 장소·물품 상태는 변경하지 않음. 응답의 민감 위치 열람도 기록. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 로그인 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | application/json |
| path | itemId | UUID | 예 | 대상 ID |

## ITEM-08. 보관 위치 이력

| 항목 | 명세 |
| --- | --- |
| Method / URL | GET /api/v1/found-items/\{itemId\}/drop-off/history |
| 접근 | 회원 |
| Request body | 없음. \{\}도 불필요 |
| Request model | 없음 |
| Response | 200 DropOffHistoryPage |
| 오류 | 공통 오류 |
| 처리 | 최신순. 민감 위치 이력 열람도 감사. 비회원에게 과거 위치·사진·설명을 제공하지 않음. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효 로그인 세션 |
| path | itemId | UUID | 예 | 대상 ID |
| query | page | integer | 아니오 | 0 이상 기본0 |
| query | size | integer | 아니오 | 1\~100 기본20 |

## ITEM-09. 만료 재등록

| 항목 | 명세 |
| --- | --- |
| Method / URL | POST /api/v1/found-items/\{itemId\}/repost |
| 접근 | 작성자 |
| Request body | 없음. \{\}도 불필요 |
| Request model | 없음 |
| Response | 200 FoundItemDetail |
| 오류 | 공통 오류, 409 ITEM\_NOT\_EXPIRED |
| 처리 | EXPIRED만 POSTED로 전환, postedAt=현재·expiresAt=30일 후·closedAt=null. hidden 유지. 감사·매칭 재평가. 삭제된 메시지 복구하지 않음. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 로그인 세션의 CSRF 토큰 |
| path | itemId | UUID | 예 | 대상 ID |

## ITEM-10. 내 게시물

| 항목 | 명세 |
| --- | --- |
| Method / URL | GET /api/v1/me/found-items |
| 접근 | 회원 |
| Request body | 없음. \{\}도 불필요 |
| Request model | 없음 |
| Response | 200 FoundItemPage |
| 오류 | 공통 오류 |
| 처리 | 본인 게시물만, statuses 생략 시 전체 상태. hidden 포함. 위치와 민감사진 URL은 별도 조회. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효 로그인 세션 |
| query | statuses | ItemStatus\[\] | 아니오 | 반복 쿼리 statuses=POSTED&statuses=EXPIRED, enum만 |
| query | page | integer | 아니오 | 0 이상 기본0 |
| query | size | integer | 아니오 | 1\~100 기본20 |

## PHOTO-01. 사진 업로드

| 항목 | 명세 |
| --- | --- |
| Method / URL | POST /api/v1/photos |
| 접근 | 회원 |
| Request body | multipart form-data |
| Request model | PhotoUploadRequest |
| Response | 201 PhotoUploadResponse |
| 오류 | 공통 오류, 413 PHOTO\_TOO\_LARGE / 422 INVALID\_IMAGE |
| 처리 | 실제 디코딩·재인코딩해 EXIF GPS를 제거한 정제본만 저장. 원본은 저장소에 보관하지 않음. 다른 회원 사진 연결 불가. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 유효 로그인 세션 |
| header | X-CSRF-Token | string | 예 | 현재 로그인 세션의 CSRF 토큰 |
| header | Content-Type | string | 예 | multipart/form-data; boundary=... |

## PHOTO-02. 사진 단기 링크

| 항목 | 명세 |
| --- | --- |
| Method / URL | POST /api/v1/photos/\{photoId\}/access-url |
| 접근 | 조건부 |
| Request body | 없음. \{\}도 불필요 |
| Request model | 없음 |
| Response | 200 PhotoAccessResponse |
| 오류 | 공통 오류 |
| 처리 | 공개 비민감 물품사진은 비회원 가능. 민감사진·보관사진은 회원, 미연결사진은 업로더만. 모든 사진 URL은 만료. 발급은 CSRF 필요. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 예 | 공개사진은 익명 CSRF 세션 허용, 민감·보관·미연결사진은 로그인 필요 |
| header | X-CSRF-Token | string | 예 | 현재 로그인 또는 익명 세션 토큰 |
| path | photoId | UUID | 예 | 대상 ID |

비회원 공개사진 URL 발급도 /auth/csrf의 익명 세션·토큰은 필요하며 로그인 신원은 요구하지 않는다. 민감사진 URL 발급도 별도 로그를 기록하되 실제 소비 로그를 대체하지 않는다.

## PHOTO-03. 사진 바이트

| 항목 | 명세 |
| --- | --- |
| Method / URL | GET /api/v1/photo-access/\{accessToken\} |
| 접근 | 조건부 |
| Request body | 없음. \{\}도 불필요 |
| Request model | 없음 |
| Response | 200 binary image |
| 오류 | 공통 오류, 410 PHOTO\_LINK\_EXPIRED |
| 처리 | 발급 권한·현재 권한 모두 검사. 민감·보관사진은 발급 회원 세션에 결합. 민감사진 실제 전달마다 감사. 객체저장소 공개 URL 노출 금지. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| cookie | KAIFIND\_SESSION | string | 조건부 | 민감·보관·미연결사진은 로그인 필요 |
| path | accessToken | string | 예 | 불투명 서명 토큰. 로그·리퍼러·오류에 원문 미노출 |

성공은 image/jpeg 또는 image/png 또는 image/webp 바이트, Content-Type·Content-Length를 반환하고 실패는 JSON ErrorResponse다. URL은 60초 제안, 세션 결합 보호사진을 다른 계정이 사용하면 거절. 재조회마다 권한·감사 처리. HEAD/Range는 같은 검사 또는 405 차단, 304 응답 미사용.

## REF-01. 활성 건물 목록·집계

| 항목 | 명세 |
| --- | --- |
| Method / URL | GET /api/v1/buildings |
| 접근 | 모두 |
| Request body | 없음. \{\}도 불필요 |
| Request model | 없음 |
| Response | 200 BuildingListResponse |
| 오류 | 공통 오류 |
| 처리 | 집계 요청 시 현재 DROP\_OFF 건물의 공개 POSTED만 계산. 직접보관·hidden·deleted 제외. 게스트도 건물 단위 집계 조회 가능. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| query | includePostedCount | boolean | 아니오 | 기본 false |

## REF-02. 활성 카테고리

| 항목 | 명세 |
| --- | --- |
| Method / URL | GET /api/v1/categories |
| 접근 | 모두 |
| Request body | 없음. \{\}도 불필요 |
| Request model | 없음 |
| Response | 200 CategoryListResponse |
| 오류 | 공통 오류 |
| 처리 | 민감 여부는 서버 기준정보 sensitive로 결정. 클라이언트가 게시물에서 변경 불가. |

### Parameter

| 위치 | 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| - | 없음 | - | - | 경로·쿼리·필수 헤더 없음 |

## 2. Request models

### CreateFoundItemRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| categoryId | UUID | 예 | 활성 카테고리 |
| title | string | 예 | 1\~100자 |
| description | string | 예 | 1\~2000자 |
| foundBuildingId | UUID | 예 | 발견 건물, 활성 참조 |
| foundLocationDescription | string | 예 | 1\~300자 발견 지점 |
| foundAt | date-time | 예 | 미래 불가 |
| photos | PhotoAttachmentInput\[\] | 예 | 1\~5개, 중복 photoId 불가 |
| dropOff | DropOffInput | 예 | 조건부 필드 검증 |

### PhotoAttachmentInput

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| photoId | UUID | 예 | 본인 미연결 업로드 또는 수정 대상에 이미 연결된 사진 |
| altText | string | 예 | 1\~200자, 물품·보관 사진 공통 |

### DropOffInput

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| mode | enum | 예 | DROP\_OFF/KEPT\_BY\_FINDER |
| buildingId | UUID | 조건부 | DROP\_OFF 필수·활성 건물, 직접 보관이면 필드 금지 |
| spotDescription | string | 조건부 | DROP\_OFF 필수 1\~300자, 직접 보관이면 필드 금지 |
| photo | PhotoAttachmentInput 또는 null | 아니오 | DROP\_OFF만 허용. PUT에서 생략/null이면 사진 없음. 직접 보관이면 필드 금지 |

### UpdateFoundItemRequest

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| categoryId | UUID | 아니오 | 활성 카테고리 |
| title | string | 아니오 | 1\~100자 |
| description | string | 아니오 | 1\~2000자 |
| foundBuildingId | UUID | 아니오 | 활성 건물 |
| foundLocationDescription | string | 아니오 | 1\~300자 |
| foundAt | date-time | 아니오 | 미래 불가 |
| photos | PhotoAttachmentInput\[\] | 아니오 | 전달 시 전체 교체, 최종 1\~5장 |

PATCH는 최소 한 필드 필요, null 불가. status/hidden/finderId/collectedBy/sensitive/dropOff 등 미정의 필드는 400. 선택값 생략은 기존 유지. 사진 목적 ITEM/DROP\_OFF를 서버에서 연결 시 검사하고 재사용·남의 업로드를 거절한다.

### PhotoUploadRequest (multipart)

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| file | binary | 예 | 실제 디코딩 가능한 JPEG/PNG/WebP, 최대 10MB 제안 |
| purpose | enum | 예 | ITEM/DROP\_OFF, 다른 용도로 연결 불가 |

### Request body 예시

등록:

```json
{
  "categoryId": "1e67e104-d975-4e8d-a9dc-826b408b6c9f",
  "title": "검은색 이어폰",
  "description": "검은 케이스의 무선 이어폰",
  "foundBuildingId": "9c265c1e-f17a-456d-8931-5560ea0010c2",
  "foundLocationDescription": "1층 로비",
  "foundAt": "2026-11-02T12:00:00+09:00",
  "photos": [
    {
      "photoId": "d14764b7-46a5-4bca-976e-09036e89010f",
      "altText": "검은 이어폰 케이스"
    }
  ],
  "dropOff": {
    "mode": "DROP_OFF",
    "buildingId": "9c265c1e-f17a-456d-8931-5560ea0010c2",
    "spotDescription": "안내 데스크"
  }
}
```

수정:

```json
{
  "title": "검은색 무선 이어폰"
}
```

보관 방식 변경:

```json
{
  "mode": "KEPT_BY_FINDER"
}
```

업로드: form-data file=(선택 이미지), purpose=ITEM. JSON이 아니며 나머지 body 없는 API는 요청 본문을 보내지 않는다.

## 3. Response models

### FoundItemSummary

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| itemId | UUID | 예 | 물품 ID |
| category | CategorySummary | 예 | 기존 비활성 참조도 이름·ID 보존 |
| title | string | 예 | 제목 |
| status | ItemStatus | 예 | POSTED/COLLECTED/EXPIRED |
| foundBuilding | BuildingSummary | 예 | 발견 건물 |
| foundAt | date-time | 예 | 발견 시각 |
| createdAt | date-time | 예 | 최초 등록 |
| photos | PhotoMetadata\[\] | 예 | 민감 물품 비회원은 \[\]. URL 없음 |
| sensitive | boolean | 예 | 서버 민감 판정 |
| hidden | boolean | 예 | 공개 결과 false |

### FoundItemDetail extends FoundItemSummary

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| description | string | 예 | 설명 |
| analysisStatus | ProcessingStatus | 예 | 현재 공개 제목·설명의 분석 상태. PENDING / PROCESSING / READY / FAILED. 신고 집계 상태·번역문·키워드는 공개하지 않음 |
| foundLocationDescription | string | 예 | 발견 지점 |
| finder | FinderSummary | 예 | userId만 |
| updatedAt | date-time | 예 | 수정 시각 |
| postedAt | date-time | 예 | 현재/마지막 POSTED 기간 시작 |
| expiresAt | date-time | 예 | postedAt+30일 |
| closedAt | date-time 또는 null | 예 | 수거/만료 종료 시각. POSTED는 null |

### FinderSummary

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| userId | UUID | 예 | 작성자 식별자. 이름·이메일·전화번호 없음 |

### PhotoMetadata

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| photoId | UUID | 예 | 사진 ID |
| altText | string | 예 | 대체 텍스트 |
| accessRequiresLogin | boolean | 예 | 민감·보관 사진은 true |

보관사진은 FoundItemSummary/[Detail.photos](http://Detail.photos)에 포함하지 않는다. 민감사진 metadata/altText도 비회원에게 제공하지 않는다. 생성·수정 응답도 이 공개 모델을 사용하고 보관 정보는 별도 API로 읽는다.

### DropOffResponse

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| mode | enum | 예 | DROP\_OFF/KEPT\_BY\_FINDER |
| building | BuildingSummary 또는 null | 예 | 직접 보관 null |
| spotDescription | string 또는 null | 예 | 직접 보관 null |
| photo | PhotoMetadata 또는 null | 예 | 보관사진 metadata, URL 없음 |
| updatedAt | date-time | 예 | 변경 시각 |

### DropOffHistoryEntry

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| historyId | UUID | 예 | 이력 ID |
| changedByUserId | UUID | 예 | 행위자 |
| changedAt | date-time | 예 | 변경 시각 |
| before | DropOffResponse 또는 null | 예 | 최초 등록이면 null |
| after | DropOffResponse | 예 | 변경 후 |

### FoundItemPage / DropOffHistoryPage

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| items | FoundItemSummary\[\] 또는 DropOffHistoryEntry\[\] | 예 | 해당 API 배열 |
| page | integer | 예 | 0부터 |
| size | integer | 예 | 요청 크기 |
| totalElements | integer | 예 | 접근 가능한 전체 건수 |
| totalPages | integer | 예 | ceil(totalElements/size), 0건은 0 |

### PhotoUploadResponse

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| photoId | UUID | 예 | 정제 완료 사진 ID |
| purpose | enum | 예 | ITEM/DROP\_OFF |
| contentType | string | 예 | 정제본 MIME |
| sizeBytes | integer | 예 | 정제본 크기 |
| width | integer | 예 | 너비 |
| height | integer | 예 | 높이 |
| unattachedExpiresAt | date-time | 예 | 미연결 정리 시각. 24시간 제안 |

### PhotoAccessResponse

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| url | string URI | 예 | 동일 서비스 HTTPS 단기 프록시 절대 URL |
| expiresAt | date-time | 예 | 발급 후 60초 제안 |
| contentType | string | 예 | 정제 이미지 MIME |

### BuildingSummary

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| buildingId | UUID | 예 | 건물 ID |
| code | string | 예 | 캠퍼스 코드 |
| nameKo | string | 예 | 한국어명 |
| nameEn | string | 예 | 영어명 |
| active | boolean | 예 | 활성 여부 |

### BuildingListResponse

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| items | BuildingCountSummary\[\] | 예 | 활성 건물 |

### BuildingCountSummary extends BuildingSummary

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| postedCount | integer | 조건부 | includePostedCount=true이면 제공, 비회원 포함. 개별 보관 정보는 미포함 |

### CategorySummary

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| categoryId | UUID | 예 | 카테고리 ID |
| nameKo | string | 예 | 한국어명 |
| nameEn | string | 예 | 영어명 |
| active | boolean | 예 | 활성 여부 |
| sensitive | boolean | 예 | 서버 민감 분류. 생성 후 변경 미지원 |

### CategoryListResponse

| 필드 | 타입 | 필수 | 검증·설명 |
| --- | --- | --- | --- |
| items | CategorySummary\[\] | 예 | 활성 카테고리 |

### Response 예시

사진 업로드:

```json
{
  "photoId": "d14764b7-46a5-4bca-976e-09036e89010f",
  "purpose": "ITEM",
  "contentType": "image/jpeg",
  "sizeBytes": 245020,
  "width": 1280,
  "height": 960,
  "unattachedExpiresAt": "2026-11-03T13:00:00+09:00"
}
```

직접 보관 조회:

```json
{
  "mode": "KEPT_BY_FINDER",
  "building": null,
  "spotDescription": null,
  "photo": null,
  "updatedAt": "2026-11-02T13:10:00+09:00"
}
```

사진 URL:

```json
{
  "url": "https://kaifind.example.com/api/v1/photo-access/example-opaque-token",
  "expiresAt": "2026-11-02T13:11:00+09:00",
  "contentType": "image/jpeg"
}
```

빈 페이지:

```json
{
  "items": [],
  "page": 0,
  "size": 20,
  "totalElements": 0,
  "totalPages": 0
}
```

오류 공통 구조:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "입력값을 확인해주세요.",
  "fieldErrors": [
    {
      "field": "photos",
      "code": "MIN_SIZE",
      "message": "물품 사진을 1장 이상 등록해주세요."
    }
  ]
}
```

204는 본문 없음, PHOTO-03 성공은 이미지 바이트다.

## 4. 내부 작업·보존 정책

| 작업 | 처리 |
| --- | --- |
| FR-25 만료 | 매일 저사용 시간에 POSTED이며 postedAt+30일 경과한 물품을 EXPIRED로 변경. 수거와 경합하면 조건부 갱신. 작성자 만료 알림·감사 기록 |
| 순서 | 만료 검사 완료 후 별도 저장소 DB 백업. 복구 점검은 운영 검증 |
| 직접 보관 | SRS 5.2 미정. 우선 일반 30일 만료 적용하는 초안. 장기 유지·인계 요구는 확정하지 않음 |
| 재등록 | postedAt=현재, expiresAt=+30일. 수거취소 후 재게시 기간도 새 시각으로 계산하는 제안 |
| 종료 | COLLECTED 또는 EXPIRED 시 closedAt. 메시지 즉시 삭제·오픈 중에만 필요한 개인정보 제거. 재등록/수거취소 시 삭제정보 복구 없음 |
| 보존 | 종료 후 1년 물품·사진·발견/보관 위치·변경 이력 보관. 수거 기록·감사 로그 1년. 물품 삭제 시 후보 삭제 |
| 업로드 | GPS 없는 정제본만 저장, 미연결 24시간 후 정리(제안), 연결 사진은 물품 주기 |
| 링크 | 숨김·삭제·보호등급 변경을 실제 소비 시 재검사. 만료 링크 410. 원본 저장소 URL은 노출하지 않음 |
| 매칭 | 생성·수정·재등록 시 category 동일 AND foundDate>=lostDateFrom AND (발견 건물 일치 OR 공통 키워드). 분실 종료일 상한 임의 추가 금지. 신규 후보만 알림 |
| 공개조회 | 기본 POSTED만. 명시적 상태 필터로 종료 물품 조회 가능, hidden은 공개 제외 |
| 동시성 | 등록·사진연결·위치변경·상태전환은 트랜잭션, 사진 중복 연결 방지. 만료·수거·재등록 상태 경합 단일 전환 |

## 5. 구현 확인 기준

| 상황 | 기대 결과 |
| --- | --- |
| 필수값·사진·보관위치/직접보관 등록 | POSTED·검색 노출·매칭 |
| 사진0장/보관건물·설명 누락/직접보관과 위치 혼용 | 400 필드 오류 |
| 남의 사진/다른 목적 사진 연결 | 403/400 연결 금지 |
| 비회원 검색·상세·이력·보관사진 | 보관정보·민감사진/alt 미노출 |
| 민감사진 URL 다른 계정 재사용 | 거절 |
| 민감사진 실제 두 번 조회 | 각 열람 감사. 로그 실패 시 미전달 |
| GPS 포함 사진 | 저장·다운로드 정제본 GPS 없음 |
| 기본 검색 | 최신순 공개 POSTED만 |
| 명시적 COLLECTED/EXPIRED 필터 | 해당 상태 가능, hidden 제외 |
| 위치 변경 | 과거·새 위치 이력, 발견 장소·상태 유지 |
| 30일 POSTED | 일일 만료·알림·감사 후 백업 |
| EXPIRED 재등록 | POSTED·새30일·hidden 유지 |
| 일반 수정으로 status/hidden 변경 | 400 |
| 건물 집계 | 현재 DROP\_OFF 공개 POSTED만, 직접보관·숨김·삭제 제외 |
| 성능 | 검색 화면95% 2초·주요 콘텐츠3초·사진1장 업로드5초. 동시 사용자 수 미정 |

## 6. 제안값·미정 사항

- 텍스트 길이, 사진10MB·최대5장, 미연결24시간, 단기링크60초는 설계 제안이다.
- 검색 건물=발견 건물·날짜=발견일로 제안했다. 보관 건물 필터는 별도 정책 확정 필요.
- 직접 보관의 30일 만료는 SRS 미정이며 우선 일반 규칙 적용 초안이다.
- 사용자 삭제는 외부 접근을 즉시 차단하는 논리 삭제로 정의한다. 기존 종료 물품의 보존 만료는 기존 closedAt+1년을 연장하지 않는다. 미종료 물품 삭제는 deletedAt+1년 보존을 제안하며 오픈 중에만 필요한 개인정보·메시지·후보는 즉시 제거한다. 감사로그에 사진·상세 위치 원문을 중복 보관하지 않는다.
- 메시지는 SRS 즉시 삭제 원칙을 따른다. 분쟁을 위한 유예 보존을 도입하려면 SRS 5.2 정책 확정이 필요하다.

## 7. 추가 응답 예시·접근 세부 규칙

FoundItemDetail은 ITEM-02/03/04/09에서 공통으로 사용한다.

2026-11-08: analysisStatus를 필수로 추가한다. 공개 원본의 현재 제목·설명만 대상으로 PENDING / PROCESSING / READY / FAILED를 반환하며 내부 SUPERSEDED는 노출하지 않는다. 원본 등록·수정과 분석 요청은 같은 트랜잭션으로 저장하고 번역은 응답 후 실행한다. 다른 사용자의 신고 집계 상태, 번역문·키워드·모델 경로는 응답하지 않는다. [구현·인계 계약](../design/translation-keyword-implementation-plan.md)을 따른다.

```json
{
  "itemId": "a4f534bf-f4e0-4f44-95ba-5e7aa85b3224",
  "category": {
    "categoryId": "1e67e104-d975-4e8d-a9dc-826b408b6c9f",
    "nameKo": "전자기기",
    "nameEn": "Electronics",
    "active": true,
    "sensitive": false
  },
  "title": "검은색 이어폰",
  "status": "POSTED",
  "foundBuilding": {
    "buildingId": "9c265c1e-f17a-456d-8931-5560ea0010c2",
    "code": "N1",
    "nameKo": "예시 건물",
    "nameEn": "Example building",
    "active": true
  },
  "foundAt": "2026-11-02T12:00:00+09:00",
  "createdAt": "2026-11-02T13:00:00+09:00",
  "photos": [
    {
      "photoId": "d14764b7-46a5-4bca-976e-09036e89010f",
      "altText": "검은 이어폰 케이스",
      "accessRequiresLogin": false
    }
  ],
  "sensitive": false,
  "hidden": false,
  "description": "검은 케이스의 무선 이어폰",
  "analysisStatus": "PENDING",
  "foundLocationDescription": "1층 로비",
  "finder": {
    "userId": "c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed"
  },
  "updatedAt": "2026-11-02T13:00:00+09:00",
  "postedAt": "2026-11-02T13:00:00+09:00",
  "expiresAt": "2026-12-02T13:00:00+09:00",
  "closedAt": null
}
```

보관 위치 조회/변경 공통 응답:

```json
{
  "mode": "DROP_OFF",
  "building": {
    "buildingId": "9c265c1e-f17a-456d-8931-5560ea0010c2",
    "code": "N1",
    "nameKo": "예시 건물",
    "nameEn": "Example building",
    "active": true
  },
  "spotDescription": "안내 데스크",
  "photo": null,
  "updatedAt": "2026-11-02T13:10:00+09:00"
}
```

건물·카테고리 응답:

```json
{
  "items": [
    {
      "buildingId": "9c265c1e-f17a-456d-8931-5560ea0010c2",
      "code": "N1",
      "nameKo": "예시 건물",
      "nameEn": "Example building",
      "active": true,
      "postedCount": 3
    }
  ]
}
```

```json
{
  "items": [
    {
      "categoryId": "1e67e104-d975-4e8d-a9dc-826b408b6c9f",
      "nameKo": "전자기기",
      "nameEn": "Electronics",
      "active": true,
      "sensitive": false
    }
  ]
}
```

모든 위치·이력·사진 API에서도 hidden 물품은 작성자·관리자만 접근할 수 있고 다른 사용자에게 404다. deleted 물품은 기존 단기 링크를 포함해 모든 일반 조회에서 404다. 보관 이력의 과거 사진도 현재 사진과 동일한 보호 정책을 적용하며 물품 연결이 해제되었다고 공개사진으로 바뀌지 않는다. 민감 분류에서 비민감 분류로 게시물을 변경해도 기존 사진의 보호 라벨은 유지한다. 그런 사진의 비회원 URL 발급은 거절하고, 공개 목록·상세의 photos에서도 해당 사진의 metadata·altText를 제외한다. 이 경우에도 로그인 회원의 실제 열람은 SENSITIVE\_PHOTO\_VIEWED로 기록한다.

사진 업로드의 altText는 연결 시 PhotoAttachmentInput에서 받아 저장하므로 업로드 즉시 이미지가 화면에 표시된다면 파일 선택 UI의 임시 대체 텍스트를 사용한다. 파일 바이트나 EXIF를 API 오류·감사 로그에 넣지 않는다.


## ITEM-03 구현 보충 (2026-11-13)

[전체 구조·구현 안내](../design/found-items.md). 등록만 기존 보호 트랜잭션으로 연결했다.
활성 카테고리·건물, timezone 포함 foundAt, 물품사진 1~5장 및 최초 보관 정보를 검증한다.
타인 사진은 403 PHOTO_FORBIDDEN, 재사용 사진은 409 PHOTO_ALREADY_ATTACHED,
없는/비활성 참조·잘못된 사진 목적·미연결 만료는 400 INVALID_REFERENCE다.
분석 요청·최초 보관 이력·사진 연결·구독 스냅샷·감사를 원본과 함께 커밋한다.
실제 번역·후보 생성은 기존 워커가 수행하며 등록 응답의 analysisStatus와 MATCH-01로 진행을 확인한다.
등록 응답에는 보관사진·보관 위치를 넣지 않는다. Location 대상의 상세 조회는 아직 후속 구현 범위다.
