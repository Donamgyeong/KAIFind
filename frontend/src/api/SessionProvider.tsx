import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ApiError, createApi } from "./client";
import { SessionContext } from "./session-context";
import type { Language, User } from "./types";

function storedLanguage(): Language {
  return localStorage.getItem("kaifind-language") === "en" ? "en" : "ko";
}

export default function SessionProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState(storedLanguage);
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [sessionError, setSessionError] = useState<unknown>(null);
  const [revision, bumpRevision] = useState(0);
  const [api] = useState(() => {
    const instance = createApi(() => {
      instance.setSession();
      setUser(null);
      bumpRevision((previous) => previous + 1);
    });
    instance.setLanguage(storedLanguage());
    return instance;
  });

  const applyLanguage = useCallback(
    (value: Language) => {
      api.setLanguage(value);
      localStorage.setItem("kaifind-language", value);
      setLang(value);
    },
    [api],
  );

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const refreshUser = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const value = await api.request<User>("/auth/me", {
          signal,
          anonymous: true,
        });
        if (signal?.aborted) return;
        setUser(value);
        applyLanguage(value.language);
        setSessionError(null);
      } catch (error) {
        if (signal?.aborted) return;
        if (error instanceof ApiError && error.status === 401) {
          setUser(null);
          setSessionError(null);
        } else {
          setSessionError(error);
        }
      } finally {
        if (!signal?.aborted) setChecking(false);
      }
    },
    [api, applyLanguage],
  );

  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(() => {
      if (!controller.signal.aborted) return refreshUser(controller.signal);
    });
    return () => controller.abort();
  }, [refreshUser]);

  async function signIn(mockAccountId: string) {
    const result = await api.request<{ user: User; csrfToken: string }>(
      "/auth/mock/login",
      {
        method: "POST",
        body: { mockAccountId },
        anonymous: true,
      },
    );
    api.setSession(result.csrfToken);
    setUser(result.user);
    setSessionError(null);
    applyLanguage(result.user.language);
    bumpRevision((value) => value + 1);
  }

  async function signOut() {
    await api.request("/auth/logout", { method: "POST" });
    api.setSession();
    setUser(null);
    bumpRevision((value) => value + 1);
  }

  async function changeLanguage(value: Language) {
    if (user) {
      const profile = await api.request<User>("/me/profile", {
        method: "PATCH",
        body: { language: value },
      });
      setUser(profile);
    }
    applyLanguage(value);
  }

  return (
    <SessionContext.Provider
      value={{
        api,
        user,
        checking,
        sessionError,
        revision,
        lang,
        t: (ko, en) => (lang === "ko" ? ko : en),
        signIn,
        signOut,
        changeLanguage,
        refreshUser,
      }}
    >
      {children}
    </SessionContext.Provider>
  );
}
