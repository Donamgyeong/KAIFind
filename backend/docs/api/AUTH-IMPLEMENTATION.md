# Auth 실행 설정

5개 Auth 엔드포인트는 PostgreSQL 서버 세션을 사용한다. 목업 로그인은 합성 계정만 제공하며 외부 SSO에는 연결하지 않는다. 다른 도메인 라우터의 인증·인가 연동은 별도 작업이다.

## 필수 설정

- `DATABASE_URL`: 기존 PostgreSQL 연결 설정.
- `AUTH_ENCRYPTION_KEY`: base64 인코딩한 32바이트 난수. CSRF 토큰을 AES-256-GCM으로 암호화한다. 모든 서버 프로세스가 같은 값을 사용해야 하며 재시작 시 유지해야 한다. 변경 시 기존 세션의 토큰을 복호화할 수 없으므로 세션을 함께 폐기해야 한다.
- `APP_ENV`: 기본 `production`. 목업을 허용하는 값은 `local`, `test`, `demo`.
- `MOCK_AUTH_ENABLED`: 기본 비활성. 위 환경에서 `true`를 명시해야 목업 계정 목록과 로그인이 활성화된다.
- `AUTH_ALLOWED_ORIGINS`: 상태 변경 요청을 허용할 정확한 origin을 쉼표로 구분한다. 예: `https://localhost:3000`. Origin이 없는 요청은 허용한다. 와일드카드는 사용하지 않는다.

키 생성 예:

```sh
python -c 'import base64, secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())'
```

생성한 키는 배포 환경의 비밀 설정에 보관한다. 애플리케이션은 `.env`를 자동으로 읽지 않는다. Compose 사용 시 위 환경변수를 backend 컨테이너에도 전달해야 한다.

## 마이그레이션과 브라우저

```sh
python -m alembic upgrade head
```

최신 revision `20261103_0002`는 로그인 요청 제한용 테이블을 추가한다. 기존 사용자는 첫 로그인 때 `mockSubject`로 조회하거나 생성하므로 별도 사용자 seed 명령은 필요 없다. 가상 계정 정의와 최초 역할은 서버의 `DEFAULT_ACCOUNTS`에서 관리한다. 기존 사용자의 역할은 로그인으로 덮어쓰지 않는다.

세션 쿠키는 모든 환경에서 `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`로 발급한다. 브라우저 통신은 HTTPS를 사용한다. 별도 origin의 프런트엔드를 사용하면 credentials 허용 CORS 설정도 배포에서 적용해야 한다.

## 동작

- 익명·로그인 세션의 미활동 만료는 30분, 절대 만료는 생성 후 12시간이다.
- `/auth/me` 인증 성공 시에만 활동 시각을 갱신한다. 이후 보호 API는 동일한 서비스 처리를 연동해야 한다.
- 로그인은 현재 세션을 잠그고 사용자 조회·생성, 기존 세션 폐기, 새 세션 생성을 한 트랜잭션에서 처리한다.
- 로그인 제한은 IP당 60초 구간에 30회다. 형식 오류도 횟수에 포함한다. PostgreSQL 잠금으로 여러 프로세스에서 한도를 공유한다.
- IP는 ASGI 요청의 client 주소를 사용한다. 리버스 프록시 배포 시 신뢰할 프록시와 forwarded header 처리를 서버에서 정확히 설정해야 한다.
- 요청·오류 응답은 `Cache-Control: no-store`를 사용한다. 오류는 `ErrorResponse`이며 미지원 언어는 한국어로 처리한다.
- 만료 세션은 해당 쿠키가 다시 사용될 때 정리하며, 제한 버킷은 다음 로그인 요청 시 만료된 행을 정리한다. 사용되지 않는 오래된 세션의 일괄 정리는 별도 운영 작업이다.

## 테스트

`tests/README.md` 참고. 서비스 테스트는 SQLite나 메모리 대체 저장소 없이 마이그레이션된 PostgreSQL을 사용한다.
