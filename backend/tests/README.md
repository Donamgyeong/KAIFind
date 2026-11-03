# Auth 테스트

프로젝트 의존성이 설치된 Python 3.11 이상에서 backend 디렉터리를 기준으로 실행합니다.

```sh
python -m pytest tests/test_auth_models.py tests/test_auth_params.py tests/test_auth_contract.py -q
```

- `test_auth_models.py`: 계정 키 경계·타입·권한 필드 주입, 사용자 응답 타입, KST 시간 직렬화.
- `test_auth_params.py`: 필수 파라미터 누락 시 서버 예외가 발생하지 않는지와 OpenAPI 계약.
- `test_auth_contract.py`: 실제 Auth 라우터를 호출하는 HTTP 인수 테스트. 서비스 미구현 때문에 strict xfail로 표시했습니다. 통과하기 시작하면 XPASS가 실행을 실패시키므로 해당 테스트의 `@pending`을 제거합니다. 실패 상세는 `-rx`, 실제 실패로 확인하려면 `--runxfail`을 사용합니다. 테스트는 계정 목록의 첫 활성 계정을 사용하며, 구현 후에는 격리된 테스트 환경과 합성 계정 seed를 준비해야 합니다.

현재 파라미터 누락의 422는 임시 동작입니다. 인증 의존성과 오류 변환을 구현할 때 `test_auth_params.py`의 해당 회귀 테스트를 최종 401/403 계약으로 변경합니다.

## 아직 코드로 검증하지 않는 항목

다음 항목은 실제 서비스·저장소·설정과 clock 주입 지점이 만들어진 뒤 PostgreSQL 통합 테스트로 추가합니다. HTTP 테스트를 통과해도 아래 항목까지 검증된 것은 아닙니다.

- 미활동·절대 만료 직전/정각/직후, 활동 갱신과 절대 만료 상한.
- CSRF·계정 목록 조회 시 활동 시간 유지.
- 첫 로그인 사용자 생성 수, seed 역할과 현재 DB 역할 유지, 비활성 계정.
- 목업 비활성화·운영 환경의 404, 빈 계정 목록.
- IP별 rate limit, 시간 경과 후 해제, 동시 요청의 원자적 제한.
- 동시 첫 로그인에서 사용자 1개 및 `isNewUser=true` 1회.
- 세션 교체 중 실패 시 트랜잭션 롤백과 기존 세션 유지.
- 로그아웃·세션 교체와 활동 갱신 경합에서 폐기 세션 부활 방지.
- 서버 오류의 민감정보 비노출, 실제 번역 문구와 오류 코드의 언어 간 동일성.

기존 `test_schema.py`는 별도 PostgreSQL 스키마 테스트입니다. 해당 테스트의 `TEST_DATABASE_URL` 안전장치와 롤백 규칙을 따릅니다.
