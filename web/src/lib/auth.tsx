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
import { setDisplayTimezone } from "./dates";

type AuthState =
  | { status: "loading"; user: null }
  | { status: "anonymous"; user: null }
  | { status: "authenticated"; user: UserInfo };

type AuthContextValue = AuthState & {
  signIn: (session: Authenticated) => void;
  signOut: () => Promise<void>;
  /** Обновить данные пользователя после правок в личном кабинете (имя, фото, email). */
  setUser: (user: UserInfo) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading", user: null });

  // Даты везде показываются в часовом поясе из профиля — выставляем его до отрисовки (lib/dates).
  const setUser = useCallback((user: UserInfo) => {
    setDisplayTimezone(user.timezone);
    setState({ status: "authenticated", user });
  }, []);

  const signIn = useCallback((session: Authenticated) => {
    setAccessToken(session.access_token);
    setDisplayTimezone(session.user.timezone);
    setState({ status: "authenticated", user: session.user });
    // Фото профиля в токене нет — подтягиваем полные данные.
    identity
      .me()
      .then((user) => {
        setDisplayTimezone(user.timezone);
        setState((s) => (s.status === "authenticated" && s.user.id === user.id ? { status: "authenticated", user } : s));
      })
      .catch(() => {});
  }, []);

  const signOut = useCallback(async () => {
    try {
      await identity.logout();
    } finally {
      setAccessToken(null);
      setDisplayTimezone(null);
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
    () => ({ ...state, signIn, signOut, setUser }),
    [state, signIn, signOut, setUser],
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
  teacher: "Учитель",
  moderator: "Модератор",
  admin: "Администратор",
};
