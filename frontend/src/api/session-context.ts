import { createContext, useContext } from "react";
import type { Api } from "./client";
import type { Language, User } from "./types";

export type Translate = (ko: string, en: string) => string;

export interface Session {
  api: Api;
  user: User | null;
  checking: boolean;
  sessionError: unknown;
  revision: number;
  lang: Language;
  t: Translate;
  signIn: (accountId: string) => Promise<void>;
  signOut: () => Promise<void>;
  changeLanguage: (lang: Language) => Promise<void>;
  refreshUser: () => Promise<void>;
}

export const SessionContext = createContext<Session | null>(null);

export function useSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error("SessionProvider is missing");
  return session;
}
