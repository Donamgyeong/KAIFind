import { useCallback, useEffect, useState } from "react";
import { useSession } from "./session-context";

interface Result<T> {
  key: string;
  scope: string;
  data?: T;
  error?: unknown;
}

export function useRemote<T>(path: string | null, anonymous = false) {
  const { api, lang, revision } = useSession();
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<Result<T>>();
  const scope = JSON.stringify([path, revision]);
  const key = JSON.stringify([scope, lang, version]);
  const reload = useCallback(() => setVersion((previous) => previous + 1), []);

  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    void api.request<T>(path, { signal: controller.signal, anonymous }).then(
      (data) => {
        if (!controller.signal.aborted) setResult({ key, scope, data });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setResult({ key, scope, error });
      },
    );
    return () => controller.abort();
  }, [api, anonymous, key, path, scope]);

  const data = result?.scope === scope ? result?.data : undefined;
  const current = result?.key === key;
  return {
    data,
    error: current ? result?.error : undefined,
    loading: path !== null && !current && !data,
    reload,
  };
}

export function useVisiblePolling(
  reload: () => void,
  enabled: boolean,
  intervalMs = 5000,
) {
  useEffect(() => {
    if (!enabled) return;
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") reload();
    }, intervalMs);
    return () => window.clearInterval(interval);
  }, [reload, enabled, intervalMs]);
}
