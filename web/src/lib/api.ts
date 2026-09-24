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

// ---- classroom ----

export type Group = {
  id: string;
  kind: "class" | "group";
  mode: "school" | "tutor";
  title: string;
  subject: string | null;
  description: string;
  archived: boolean;
  student_count: number;
  created_at: string;
};

export type Member = { student_id: string; full_name: string; login: string | null; joined_at: string };

export type GroupDetail = Group & { members: Member[] };

export type Student = {
  student_id: string;
  full_name: string;
  login: string | null;
  status: "active" | "pending";
  source: "invite" | "manual" | "request" | "marketplace";
  managed: boolean;
  group_ids: string[];
};

export type StudentCredentials = { student: Student; login: string | null; password: string | null };

export type Invitation = { id: string; email: string; group_id: string | null; expires_at: string; created_at: string };

export type InvitationPublic = {
  status: "valid" | "expired" | "used" | "revoked";
  teacher_name: string;
  group_title: string | null;
  group_kind: "class" | "group" | null;
};

export type MyTeacher = {
  link_id: string;
  teacher_id: string;
  full_name: string;
  status: "active" | "pending";
  groups: { id: string; title: string }[];
};

export type MyGroup = {
  id: string;
  title: string;
  subject: string | null;
  kind: string;
  teacher_id: string;
  teacher_name: string;
};

const CR = "/api/classroom";

export const classroom = {
  groups: (archived = false) => api<Group[]>(`${CR}/groups?archived=${archived}`),
  group: (id: string) => api<GroupDetail>(`${CR}/groups/${id}`),
  createGroup: (data: { title: string; kind: "class" | "group"; subject?: string | null }) =>
    api<Group>(`${CR}/groups`, { method: "POST", body: data }),
  updateGroup: (id: string, data: { title?: string; subject?: string | null; description?: string }) =>
    api<Group>(`${CR}/groups/${id}`, { method: "PATCH", body: data }),
  archiveGroup: (id: string) => api<Group>(`${CR}/groups/${id}/archive`, { method: "POST" }),
  restoreGroup: (id: string) => api<Group>(`${CR}/groups/${id}/restore`, { method: "POST" }),
  addMember: (groupId: string, studentId: string) =>
    api<void>(`${CR}/groups/${groupId}/members`, { method: "POST", body: { student_id: studentId } }),
  removeMember: (groupId: string, studentId: string) =>
    api<void>(`${CR}/groups/${groupId}/members/${studentId}`, { method: "DELETE" }),

  students: () => api<Student[]>(`${CR}/students`),
  createManual: (data: { full_name: string; login?: string | null; password?: string | null; group_id?: string | null }) =>
    api<StudentCredentials>(`${CR}/students/manual`, { method: "POST", body: data }),
  requestLink: (identifier: string, group_id?: string | null) =>
    api<Student>(`${CR}/students/requests`, { method: "POST", body: { identifier, group_id } }),
  renameStudent: (id: string, full_name: string) =>
    api<Student>(`${CR}/students/${id}`, { method: "PATCH", body: { full_name } }),
  resetPassword: (id: string) => api<StudentCredentials>(`${CR}/students/${id}/reset-password`, { method: "POST" }),
  unlinkStudent: (id: string) => api<void>(`${CR}/students/${id}`, { method: "DELETE" }),

  invitations: () => api<Invitation[]>(`${CR}/invitations`),
  invite: (email: string, group_id?: string | null) =>
    api<Invitation>(`${CR}/invitations`, { method: "POST", body: { email, group_id } }),
  revokeInvitation: (id: string) => api<void>(`${CR}/invitations/${id}`, { method: "DELETE" }),
  viewInvitation: (token: string) => api<InvitationPublic>(`${CR}/invitations/token/${token}`, { auth: false }),
  acceptInvitation: (token: string) => api<void>(`${CR}/invitations/token/${token}/accept`, { method: "POST" }),

  myTeachers: () => api<MyTeacher[]>(`${CR}/me/teachers`),
  myGroups: () => api<MyGroup[]>(`${CR}/me/groups`),
  acceptRequest: (linkId: string) => api<void>(`${CR}/me/requests/${linkId}/accept`, { method: "POST" }),
  declineRequest: (linkId: string) => api<void>(`${CR}/me/requests/${linkId}/decline`, { method: "POST" }),
};
