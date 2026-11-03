# 테스트 실행

Python 3.11 이상에서 프로젝트 의존성을 설치하고 별도 `kaifind_test_*` PostgreSQL DB에 마이그레이션을 적용한다.

```sh
DATABASE_URL="$TEST_DATABASE_URL" python -m alembic upgrade head
python -m pytest tests -q
```

`TEST_DATABASE_URL`은 직접 설정해야 하며, DB 이름이 `kaifind_test_`로 시작하지 않으면 통합 테스트를 거부한다. 운영 DB를 지정하지 않는다.

- `test_auth_models.py`: DB 없이 요청 필드·타입·추가 필드 거부와 응답 직렬화를 검증한다.
- `test_auth_params.py`: 파라미터 누락 시 최종 인증 오류, OpenAPI 파라미터와 204 응답을 검증한다.
- `test_auth_contract.py`: 실제 라우터를 호출해 로그인·CSRF·쿠키·로그아웃·언어별 오류 계약을 검증한다. 예상 실패 표시는 없다.
- `test_auth_service.py`: PostgreSQL에서 만료 경계·활동 갱신·권한 유지·암호화·롤백·동시 로그인·세션 폐기 경합·IP별 동시 요청 제한을 검증한다.
- `test_schema.py`: 기존 PostgreSQL 스키마 제약을 검증하며 테스트별 트랜잭션을 롤백한다.

Auth 테스트는 각 테스트 시작 시 `users`, `sessions`, `auth_login_rates`와 연결 데이터를 TRUNCATE한다. 반드시 전용 폐기 가능한 DB를 사용한다. 공유 DB에서 병렬 pytest 실행은 지원하지 않는다. DB 주소가 없으면 DB 통합 테스트는 skip되므로 전체 검증 결과로 해석하지 않는다.

테스트 clock은 `2026-11-03T10:00:00+09:00`으로 고정하며 직접 전진시킨다. 합성 계정·암호화 키·허용 origin은 fixture에서 주입하고 실제 핸들러·DB를 대체하지 않는다.

관리자 테스트도 같은 전용 DB를 사용한다. `test_admin_models.py`는 DB 없이 DTO·감사 허용목록·OpenAPI를,
`test_admin_contract.py`는 실제 HTTP·DB로 권한 즉시 반영, 쓰기 보안, 기준정보 중복,
신고 숨김, 분쟁 검토, 근거 삭제 후 제한 해제, 통계·감사 필터와 감사 실패 롤백을 검증한다.
동시 관리자 회수·게시물/분쟁 검토·카테고리 생성 경합도 포함한다.
관리자 fixture는 `buildings`, `categories`, `audit_logs`도 TRUNCATE하므로 동일 DB 병렬 실행은 금지한다.
