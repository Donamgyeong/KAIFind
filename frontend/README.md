# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## 로컬 개발

저장소 루트(`KAIFind/`)에서 아래 명령을 실행합니다. Node 버전은 `frontend/.nvmrc`의 **24.14.1**을 사용합니다.

```sh
cd frontend
nvm install
nvm use
npm ci
npm run dev
```

브라우저에서 [http://localhost:3000](http://localhost:3000)을 엽니다. `nvm`을 사용하지 않는 경우 Node 24.14.1을 설치하고 `npm ci`부터 실행합니다. 3000번 포트가 이미 사용 중이면 해당 프로그램을 종료한 뒤 다시 실행합니다.

### FastAPI 연결

처음 백엔드를 실행하는 팀원은 저장소 루트에 `example.env`를 복사해 `.env`를 만들고, [백엔드 실행 안내](../backend/README.md)의 모델 준비, DB 마이그레이션, 분석 정책 및 사진 버킷 초기화 절차를 따릅니다. 초기화한 환경에서는 저장소 루트에서 `docker compose up -d backend`로 실행할 수 있습니다.

목업 로그인을 테스트하려면 루트 `.env`에 아래 값을 사용하고, `openssl rand -base64 32`로 생성한 값을 `AUTH_ENCRYPTION_KEY`에 설정합니다. 기존 키가 있다면 그 값을 유지합니다. [인증 설정 안내](../backend/docs/api/AUTH-IMPLEMENTATION.md)

```dotenv
APP_ENV=local
MOCK_AUTH_ENABLED=true
AUTH_ALLOWED_ORIGINS=http://localhost:3000
PHOTO_PUBLIC_BASE_URL=http://localhost:3000
```

Vite는 `/api/v1` 요청을 `http://127.0.0.1:8000`으로 전달합니다. 프론트엔드 코드에서는 `fetch("/api/v1/categories")`처럼 상대 경로를 사용합니다. 두 서버가 실행 중일 때 [카테고리 API](http://localhost:3000/api/v1/categories)를 열어 JSON 응답을 확인할 수 있습니다.

로컬 로그인 테스트에는 `http://localhost:3000`을 사용합니다. 백엔드가 발급하는 `Secure` 세션 쿠키는 브라우저의 localhost 예외에 의존하며, 배포 환경에서는 HTTPS가 필요합니다. [세션 쿠키 동작](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie#secure)

## Formatting

Run `npm run format:check` from `frontend/` to check formatting, or run `npm run format` to apply it.

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(["dist"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ["./tsconfig.node.json", "./tsconfig.app.json"],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
]);
```

You can also install [eslint-plugin-react-x](https://npmx.dev/package/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://npmx.dev/package/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from "eslint-plugin-react-x";
import reactDom from "eslint-plugin-react-dom";

export default defineConfig([
  globalIgnores(["dist"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs["recommended-typescript"],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ["./tsconfig.node.json", "./tsconfig.app.json"],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
]);
```
