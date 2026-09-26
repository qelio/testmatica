"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import {
  type Authenticated,
  identity,
  refreshSession,
  setAccessToken,
  setSessionLostHandler,
  type UserInfo,
} from "./api";

type AuthState =
  | { status: "loading"; user: null }
  | { status: "anonymous"; user: null }
  | { status: "authenticated"; user: UserInfo };

type AuthContextValue = AuthState & {
  signIn: (session: Authenticated) => void;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading", user: null });

  const signIn = useCallback((session: Authenticated) => {
    setAccessToken(session.access_token);
    setState({ status: "authenticated", user: session.user });
  }, []);

  const signOut = useCallback(async () => {
    try {
      await identity.logout();
    } finally {
      setAccessToken(null);
      setState({ status: "anonymous", user: null });
    }
  }, []);

  useEffect(() => {
    setSessionLostHandler(() => setState({ status: "anonymous", user: null }));
    // При загрузке страницы восстанавливаем сессию по refresh-cookie.
    refreshSession()
      .then((session) => (session ? signIn(session) : setState({ status: "anonymous", user: null })))
      .catch(() => setState({ status: "anonymous", user: null }));
    return () => setSessionLostHandler(null);
  }, [signIn]);

  const value = useMemo(
    () => ({ ...state, signIn, signOut }),
    [state, signIn, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth вне AuthProvider");
  return ctx;
}

export const ROLE_LABELS: Record<string, string> = {
  student: "Ученик",
  teacher: "Педагог",
  moderator: "Модератор",
  admin: "Администратор",
};
