import type { Language } from "./types";

interface FieldError {
  field: string;
  code: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: FieldError[];

  constructor(
    status: number,
    code: string,
    message: string,
    fields: FieldError[],
  ) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

interface Options {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: object | FormData;
  signal?: AbortSignal;
  anonymous?: boolean;
}

export function createApi(onSessionExpired: () => void) {
  let csrf: Promise<string> | undefined;
  let language: Language = "ko";
  let epoch = 0;

  async function send<T>(
    path: string,
    options: Options = {},
    token?: string,
  ): Promise<T> {
    const headers = new Headers({ "Accept-Language": language });
    if (token) headers.set("X-CSRF-Token", token);
    const form = options.body instanceof FormData;
    if (options.body && !form) headers.set("Content-Type", "application/json");
    const response = await fetch("/api/v1" + path, {
      method: options.method ?? "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers,
      signal: options.signal,
      body: form ? (options.body as FormData) : JSON.stringify(options.body),
    });
    if (response.status === 204) return undefined as T;
    const data = response.headers
      .get("Content-Type")
      ?.includes("application/json")
      ? await response.json()
      : undefined;
    if (!response.ok) {
      throw new ApiError(
        response.status,
        data?.code ?? "HTTP_ERROR",
        data?.message ?? "",
        data?.fieldErrors ?? [],
      );
    }
    return data as T;
  }

  function token() {
    if (!csrf) {
      const pending = send<{ csrfToken: string }>("/auth/csrf").then(
        (value) => value.csrfToken,
      );
      csrf = pending;
      void pending.catch(() => {
        if (csrf === pending) csrf = undefined;
      });
    }
    return csrf;
  }

  return {
    setLanguage(value: Language) {
      language = value;
    },
    setSession(newToken?: string) {
      epoch += 1;
      csrf = newToken ? Promise.resolve(newToken) : undefined;
    },
    async request<T>(path: string, options: Options = {}): Promise<T> {
      const requestEpoch = epoch;
      try {
        const header =
          options.method && options.method !== "GET"
            ? await token()
            : undefined;
        if (requestEpoch !== epoch)
          throw new DOMException("Session changed", "AbortError");
        options.signal?.throwIfAborted();
        return await send<T>(path, options, header);
      } catch (error) {
        if (requestEpoch === epoch && error instanceof ApiError) {
          if (
            error.code === "CSRF_INVALID" ||
            error.code === "INVALID_CSRF_TOKEN"
          )
            csrf = undefined;
          if (!options.anonymous && error.status === 401) onSessionExpired();
        }
        throw error;
      }
    },
  };
}

export type Api = ReturnType<typeof createApi>;
