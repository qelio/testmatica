// Клиент API. Все запросы идут на тот же домен: Traefik направляет /api/<сервис>/... в нужный сервис.
// Access-токен хранится только в памяти; refresh-токен — в httpOnly-cookie, JS его не видит.

export type UserInfo = {
  id: string;
  email: string | null;
  login: string | null;
  full_name: string;
  roles: string[];
  teacher_mode: "school" | "tutor" | null;
  two_factor_method: string | null;
  timezone: string;
};

export type Authenticated = {
  status: "authenticated";
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: UserInfo;
};

export type TwoFactorRequired = {
  status: "2fa_required";
  challenge_id: string;
  method: string;
  destination: string;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }

  fieldErrors(): Record<string, string> {
    const fields = (this.details.fields as { field: string; message: string }[] | undefined) ?? [];
    return Object.fromEntries(fields.map((f) => [f.field, f.message]));
  }
}

let accessToken: string | null = null;
let refreshInFlight: Promise<Authenticated | null> | null = null;
let onSessionLost: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function setSessionLostHandler(handler: (() => void) | null) {
  onSessionLost = handler;
}

async function parse<T>(resp: Response): Promise<T> {
  if (resp.status === 204) return undefined as T;
  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
    const err = body?.error;
    throw new ApiError(
      resp.status,
      err?.code ?? "http_error",
      err?.message ?? "Не удалось выполнить запрос. Попробуйте ещё раз.",
      err?.details ?? {},
    );
  }
  return body as T;
}

async function send(path: string, init: RequestInit, withToken: boolean): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  if (withToken && accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  try {
    return await fetch(path, { ...init, headers, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "network_error", "Нет связи с сервером. Проверьте интернет.");
  }
}

/** Обновить access-токен по refresh-cookie. Параллельные вызовы объединяются в один запрос. */
export function refreshSession(): Promise<Authenticated | null> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const session = await parse<Authenticated>(
          await send("/api/identity/auth/refresh", { method: "POST" }, false),
        );
        accessToken = session.access_token;
        return session;
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          accessToken = null;
          return null;
        }
        throw e;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

type Options = { method?: string; body?: unknown; auth?: boolean };

/** Запрос к API. При 401 один раз пробует обновить токен и повторить. */
export async function api<T>(path: string, { method = "GET", body, auth = true }: Options = {}): Promise<T> {
  const init: RequestInit = { method, body: body === undefined ? undefined : JSON.stringify(body) };
  let resp = await send(path, init, auth);
  if (resp.status === 401 && auth) {
    const session = await refreshSession();
    if (!session) {
      onSessionLost?.();
      return parse<T>(resp);
    }
    resp = await send(path, init, auth);
  }
  return parse<T>(resp);
}

// ---- identity ----

const ID = "/api/identity";

export const identity = {
  register: (data: {
    email: string;
    password: string;
    full_name: string;
    role: "student" | "teacher";
    consent_pdn: boolean;
  }) =>
    api<{ user_id: string; challenge_id: string; destination: string }>(`${ID}/auth/register`, {
      method: "POST",
      body: data,
      auth: false,
    }),
  verifyEmail: (challenge_id: string, code: string) =>
    api<Authenticated>(`${ID}/auth/verify-email`, {
      method: "POST",
      body: { challenge_id, code },
      auth: false,
    }),
  resendCode: (challenge_id: string) =>
    api<{ status: string }>(`${ID}/auth/resend-code`, { method: "POST", body: { challenge_id }, auth: false }),
  login: (identifier: string, password: string) =>
    api<TwoFactorRequired | Authenticated>(`${ID}/auth/login`, {
      method: "POST",
      body: { identifier, password },
      auth: false,
    }),
  loginVerify: (challenge_id: string, code: string) =>
    api<Authenticated>(`${ID}/auth/login/verify`, { method: "POST", body: { challenge_id, code }, auth: false }),
  logout: () => api<void>(`${ID}/auth/logout`, { method: "POST", auth: false }),
  forgotPassword: (email: string) =>
    api<{ challenge_id: string }>(`${ID}/auth/password/forgot`, { method: "POST", body: { email }, auth: false }),
  resetPassword: (challenge_id: string, code: string, new_password: string) =>
    api<{ status: string }>(`${ID}/auth/password/reset`, {
      method: "POST",
      body: { challenge_id, code, new_password },
      auth: false,
    }),
  switchTeacherMode: (mode: "school" | "tutor") =>
    api<Authenticated>(`${ID}/me/teacher-mode`, { method: "PUT", body: { mode } }),
};

// ---- notification ----

export type NotificationItem = {
  id: string;
  kind: string;
  title: string;
  body: string;
  read_at: string | null;
  created_at: string;
};

export const notifications = {
  list: () =>
    api<{ items: NotificationItem[]; unread: number }>("/api/notification/notifications?limit=20"),
  markRead: (id: string) => api<void>(`/api/notification/notifications/${id}/read`, { method: "POST" }),
  markAllRead: () => api<void>("/api/notification/notifications/read-all", { method: "POST" }),
};
