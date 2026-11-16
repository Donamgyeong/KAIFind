# KAIFind 프론트엔드

KAIFind 프론트엔드는 **React + TypeScript + Vite**로 구성된 웹 앱입니다.

- **라우팅**은 화면별 경로를 구현할 때 React Router를 사용합니다. 현재는 [`src/App.tsx`](src/App.tsx)에서 단일 화면을 렌더링합니다.
- **스타일링**은 CSS Modules와 CSS 변수를 사용합니다. 화면과 컴포넌트의 스타일은 대응하는 `.module.css` 파일에 작성하고, 색상·글꼴·간격 같은 공통 값은 [`src/index.css`](src/index.css)에 CSS 변수로 정의합니다.

## 1. 프론트엔드 개발 설정

저장소 루트에서 아래 명령을 실행합니다. [`.nvmrc`](.nvmrc)에 지정된 Node.js 24.14.1을 사용합니다.

```sh
cd frontend
nvm install
nvm use
npm ci
```

`nvm`을 사용하지 않는 경우 Node.js 24.14.1을 설치한 뒤 `frontend/`에서 `npm ci`를 실행합니다. `package-lock.json`이 바뀌면 `npm ci`를 다시 실행합니다.

## 2. 프론트엔드 서버 실행 및 개발 명령

`frontend/`에서 개발 서버를 실행합니다.

```sh
npm run dev
```

브라우저에서 [http://localhost:3000](http://localhost:3000)을 엽니다. 3000번 포트가 사용 중이면 포트를 비운 뒤 다시 실행합니다.

| 명령                   | 설명                      |
| ---------------------- | ------------------------- |
| `npm run format`       | Prettier 포맷 적용        |
| `npm run format:check` | Prettier 포맷 검사        |
| `npm run lint`         | ESLint 검사               |
| `npm run build`        | TypeScript 검사와 빌드    |
| `npm run preview`      | 빌드 결과를 로컬에서 확인 |

## 3. 백엔드 서버 실행 및 연결

백엔드를 처음 실행하는 경우 [백엔드 README](../backend/README.md)의 환경 설정과 초기화 절차를 따릅니다. 초기화가 끝난 환경에서는 Docker Desktop을 실행한 뒤 저장소 루트에서 아래 명령을 실행합니다.

```sh
docker compose up -d backend
```

- [FastAPI 문서](http://localhost:8000/docs)가 열리면 백엔드가 실행 중입니다.
- Vite도 실행한 상태에서 [카테고리 API](http://localhost:3000/api/v1/categories)가 JSON을 응답하면 프록시가 연결된 상태입니다.
- 프론트 코드에서는 `fetch("/api/v1/categories")`처럼 상대 경로를 사용합니다. Vite가 `/api/v1`의 요청을 `http://127.0.0.1:8000`으로 전달합니다.

목업 로그인 연동 시 브라우저에서 `http://localhost:3000`을 사용하고, 저장소 루트 `.env`의 `AUTH_ALLOWED_ORIGINS`에 같은 주소가 허용돼 있는지 확인합니다. 사진 링크도 Vite를 거치게 하려면 `PHOTO_PUBLIC_BASE_URL`을 같은 주소로 설정합니다. [인증 설정 안내](../backend/docs/api/AUTH-IMPLEMENTATION.md) · [API 명세](../backend/docs/api/README.md)
