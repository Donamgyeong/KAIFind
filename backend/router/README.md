# 기능별 FastAPI 라우터

`main.py`에서 `api_router`를 등록하며, 모든 기능 API의 공통 경로는 `/api/v1`입니다.

| 모듈 | 기능 |
| --- | --- |
| auth.py | CSRF, 목업 로그인, 세션 조회, 로그아웃 |
| found_items.py | 습득물 검색·등록·수정·삭제, 보관 위치, 게시물 신고 |
| photos.py | 사진 업로드, 접근 링크, 사진 조회 |
| reference.py | 공개 건물·카테고리 목록 |
| lost_reports.py | 분실 신고 등록·조회·수정·연장·해결 |
| matching.py | 분실 신고 매칭 후보 조회 |
| profile.py | 본인 프로필 조회·설정 |
| notifications.py | 알림 수신 설정·목록·읽음 처리 |
| keyword_subscriptions.py | 키워드 구독 관리 |
| collections.py | 수거 표시·조회·취소 |
| disputes.py | 수거 이의 제기·조회 |
| messages.py | 대화 시작·목록·메시지 송수신 |
| admin.py | 권한·기준정보·신고·분쟁·통계·감사 관리 |

로컬 `docs/api` 명세의 63개 메서드·경로를 등록한 기본 구조입니다.
미구현 핸들러는 모두 HTTP 501을 반환합니다. UUID 경로 파라미터는 UUID로 검증하며,
사진 접근 토큰은 문자열로 받습니다. 요청·응답 DTO, 검색·페이지네이션 쿼리,
인증·관리자 권한·CSRF 의존성, DB 및 서비스 로직은 후속 구현 대상입니다.
미구현 라우터의 OpenAPI는 경로 구조 확인용이며 완성된 API 계약을 나타내지 않습니다.

Auth의 5개 엔드포인트는 `service/auth.py`에 세션·CSRF·사용자 처리 로직을 구현했습니다.
`schema/auth.py`는 DTO, `router/auth_params.py`는 파라미터,
`library/auth_http.py`는 요청 가드와 공통 오류 응답을 담당합니다.
설정·마이그레이션·테스트 실행법은 `docs/api/AUTH-IMPLEMENTATION.md`를 참고합니다.

새 라우터는 모듈의 `router = APIRouter(...)`에 엔드포인트를 작성한 후
`router/__init__.py`에서 `api_router.include_router(...)`로 등록합니다.

의존성이 설치된 환경에서 `uvicorn main:app --reload`로 실행하고 `/docs`에서 확인합니다.

Admin의 17개 엔드포인트와 MOD-01 회원 게시물 신고를 구현했습니다.
`schema/admin.py`는 DTO, `router/admin_params.py`는 검색 파라미터,
`library/protected_http.py`는 세션·ADMIN·CSRF·Origin 검사 및 요청 트랜잭션,
`service/admin.py`와 `service/audit.py`는 업무 처리·감사를 담당합니다.
실행·마이그레이션·검증 범위는 [관리자 구현 현황](../docs/api/ADMIN-IMPLEMENTATION.md)을 참고합니다.

Photo의 3개 엔드포인트는 `service/photos.py`에 업로드·접근 권한·단기 토큰·프록시 조회를 구현했습니다.
`library/photo_images.py`는 정제, `library/photo_storage.py`는 MinIO 연결,
`library/photo_http.py`는 오류 응답·사진 토큰 로그 마스킹을 담당합니다.
설정·정리 작업·연결 서비스 사용 범위는 [사진 API 및 MinIO](../docs/MINIO.md)를 참고합니다.
