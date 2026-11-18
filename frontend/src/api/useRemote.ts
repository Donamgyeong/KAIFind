import { useCallback, useEffect, useState } from "react";
import { useSession } from "./session-context";

interface Result<T> {
  key: string;
  data?: T;
  error?: unknown;
}

export function useRemote<T>(path: string | null, anonymous = false) {
  const { api, lang, revision } = useSession();
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<Result<T>>();
  const key = JSON.stringify([path, lang, revision, version]);
  const reload = useCallback(() => setVersion((previous) => previous + 1), []);

  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    void api.request<T>(path, { signal: controller.signal, anonymous }).then(
      (data) => {
        if (!controller.signal.aborted) setResult({ key, data });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setResult({ key, error });
      },
    );
    return () => controller.abort();
  }, [api, anonymous, key, path]);

  const current = result?.key === key ? result : undefined;
  return {
    data: current?.data,
    error: current?.error,
    loading: path !== null && !current,
    reload,
  };
}
