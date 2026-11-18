# KAIFind 프론트엔드

React, TypeScript, Vite와 React Router로 구성한 캠퍼스 분실물 웹앱입니다. Node.js 버전은 `.nvmrc`를 따릅니다.

## 로컬 실행

1. 저장소 루트에서 [백엔드 실행 안내](../backend/README.md)에 따라 Docker Compose, DB 마이그레이션, 모델·매칭 정책과 사진 저장소를 준비합니다.
2. 브라우저에서 신뢰하는 localhost 인증서와 키를 준비합니다. 예를 들어 로컬 CA가 이미 등록돼 있다면 `mkcert localhost 127.0.0.1`로 발급할 수 있습니다.
3. 백엔드에 `AUTH_ALLOWED_ORIGINS=https://localhost:3000`, `PHOTO_PUBLIC_BASE_URL=https://localhost:3000`, `NOTIFICATION_EMAIL_APP_BASE_URL=https://localhost:3000`을 설정합니다. 시연 계정은 [인증 안내](../backend/docs/api/AUTH-IMPLEMENTATION.md)에 따라 활성화합니다.
4. 이 디렉터리에서 실행합니다.

```sh
npm ci
KAIFIND_TLS_CERT=/path/to/localhost.pem KAIFIND_TLS_KEY=/path/to/localhost-key.pem npm run dev
```

브라우저에서 [KAIFind](https://localhost:3000)를 엽니다. Vite는 동일 출처의 `/api/v1`을 Compose의 FastAPI 포트 8000으로 전달합니다. 정적 빌드 배포 시에도 같은 HTTPS 호스트에 API 리버스 프록시를 두고, 페이지 경로의 직접 접근은 `index.html`로 처리합니다.

## 구조와 검증

- `src/api`는 API 요청, 세션·CSRF, 응답 타입을 관리합니다.
- `src/ui`는 화면 공통 컴포넌트와 KST 표시를 제공합니다.
- `src/pages`는 기능별 라우트 화면이고, 색상·글꼴은 `src/index.css`의 공통 스타일을 사용합니다.

```sh
npm run format:check
npm run lint
npm run build
```

## 시연 기준정보

Vite와 백엔드가 실행 중인 상태에서 시연 관리자 계정으로 건물 E/W/N 68개와 기본 카테고리를 등록합니다. 카드·지갑은 비민감으로 등록합니다. 기존 코드는 기존 서버 ID와 설정을 유지합니다. 스크립트가 활성·민감 설정 차이를 표시하면 관리자 화면에서 해당 항목의 정책을 확인할 수 있습니다.

\`\`\`sh
npm run seed:reference
\`\`\`

기본 접속 주소는 \`https://localhost:3000\`, 기본 계정은 \`admin-01\`입니다. 시연 출처와 계정이 다르면 명령 실행 시 \`KAIFIND_SEED_ORIGIN\`과 \`KAIFIND_SEED_ACCOUNT\`를 지정합니다. Node가 로컬 CA를 별도로 필요로 하면 \`NODE_EXTRA_CA_CERTS\`에 해당 CA 인증서 경로를 지정합니다.
