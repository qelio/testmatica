// Клиент API. Все запросы идут на тот же домен: Traefik направляет /api/<сервис>/... в нужный сервис.
// Access-токен хранится только в памяти; refresh-токен — в httpOnly-cookie, JS его не видит.

/** Имя по частям (решение №35); full_name — «Фамилия Имя Отчество» для показа. */
export type PersonName = { last_name: string; first_name: string; middle_name: string };

export type UserInfo = PersonName & {
  id: string;
  email: string | null;
  login: string | null;
  /** «Фамилия Имя Отчество» — так имя показывается во всех списках. */
  full_name: string;
  roles: string[];
  two_factor_method: string | null;
  timezone: string;
  email_verified?: boolean;
  managed?: boolean;
  two_factor_required?: boolean;
  avatar_url?: string | null;
  /** Нужно принять соглашение и дать согласие на обработку ПД (текущие редакции) — окно при входе. */
  consent_required?: boolean;
  /** false — почтового сервера пока нет: вход с кодом, смена email и сброс пароля «скоро». */
  email_codes?: boolean;
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

/** Действующий access-токен (для WebSocket); при необходимости обновляется. */
export async function currentAccessToken(): Promise<string | null> {
  if (accessToken) return accessToken;
  return (await refreshSession())?.access_token ?? null;
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

/** Запрос, который возвращает файл (PDF, Excel): так же с токеном и повтором при 401. */
export async function apiFile(path: string, { method = "POST", body }: Omit<Options, "auth"> = {}): Promise<Blob> {
  const init: RequestInit = { method, body: body === undefined ? undefined : JSON.stringify(body) };
  let resp = await send(path, init, true);
  if (resp.status === 401 && (await refreshSession())) resp = await send(path, init, true);
  if (!resp.ok) await parse(resp); // бросит ApiError с сообщением сервера
  return resp.blob();
}

/** Сохранить файл из ответа API на компьютер. */
export function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

import { timezone } from "@/lib/dates";
import type { Landing, LandingOut, NewsFull, NewsSummary } from "@/lib/server-api";

// ---- identity ----

const ID = "/api/identity";

export const identity = {
  features: () => api<{ email_codes: boolean }>(`${ID}/auth/features`, { auth: false }),
  me: () => api<UserInfo>(`${ID}/me`),
  updateMe: (data: { name?: PersonName; timezone?: string }) => api<UserInfo>(`${ID}/me`, { method: "PATCH", body: data }),
  setAvatar: (fileId: string | null) => api<UserInfo>(`${ID}/me/avatar`, { method: "PUT", body: { file_id: fileId } }),
  changeEmail: (email: string, password: string) =>
    api<{ challenge_id: string; destination: string }>(`${ID}/me/email`, { method: "POST", body: { email, password } }),
  confirmEmail: (challenge_id: string, code: string) =>
    api<UserInfo>(`${ID}/me/email/confirm`, { method: "POST", body: { challenge_id, code } }),
  changePassword: (current_password: string, new_password: string) =>
    api<void>(`${ID}/me/password`, { method: "POST", body: { current_password, new_password } }),
  setTwoFactor: (enabled: boolean, password: string) => api<UserInfo>(`${ID}/me/2fa`, { method: "PUT", body: { enabled, password } }),
  giveConsents: (byRepresentative: boolean) =>
    api<UserInfo>(`${ID}/me/consents`, { method: "POST", body: { accept_terms: true, consent_pdn: true, by_representative: byRepresentative } }),
  register: (data: PersonName & {
    email: string;
    password: string;
    role: "student" | "teacher";
    consent_pdn: boolean;
    accept_terms: boolean;
  }) =>
    // Без почтового сервера (решение №29) регистрация сразу открывает сессию.
    api<{ user_id: string; challenge_id: string; destination: string } | Authenticated>(`${ID}/auth/register`, {
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
};

// ---- notification ----

export type NotificationItem = {
  id: string;
  kind: string;
  title: string;
  body: string;
  payload: { starts_at?: string; new_starts_at?: string; [key: string]: unknown };
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
  paid: boolean;
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
  paid: boolean; // индивидуальные занятия платные
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
  createGroup: (data: { title: string; kind: "class" | "group"; paid: boolean; subject?: string | null }) =>
    api<Group>(`${CR}/groups`, { method: "POST", body: data }),
  updateGroup: (id: string, data: { title?: string; subject?: string | null; description?: string; paid?: boolean }) =>
    api<Group>(`${CR}/groups/${id}`, { method: "PATCH", body: data }),
  archiveGroup: (id: string) => api<Group>(`${CR}/groups/${id}/archive`, { method: "POST" }),
  /** Выйти из аккаунтов всех учеников группы на всех устройствах (оставили вход на школьных компьютерах). */
  signOutGroup: (id: string) => api<{ count: number }>(`${CR}/groups/${id}/sign-out`, { method: "POST" }),
  signOutStudent: (id: string) => api<{ count: number }>(`${CR}/students/${id}/sign-out`, { method: "POST" }),
  restoreGroup: (id: string) => api<Group>(`${CR}/groups/${id}/restore`, { method: "POST" }),
  addMember: (groupId: string, studentId: string) =>
    api<void>(`${CR}/groups/${groupId}/members`, { method: "POST", body: { student_id: studentId } }),
  removeMember: (groupId: string, studentId: string) =>
    api<void>(`${CR}/groups/${groupId}/members/${studentId}`, { method: "DELETE" }),

  students: () => api<Student[]>(`${CR}/students`),
  createManual: (data: PersonName & { login?: string | null; password?: string | null; group_id?: string | null }) =>
    api<StudentCredentials>(`${CR}/students/manual`, { method: "POST", body: data }),
  createManualBulk: (fullNames: string[], groupId?: string | null) =>
    api<{ created: StudentCredentials[]; errors: { full_name: string; message: string }[] }>(`${CR}/students/manual/bulk`, {
      method: "POST",
      body: { full_names: fullNames, group_id: groupId ?? null },
    }),
  /** PDF с карточками входа — только для что созданных учеников (пароли больше нигде не показываются). */
  credentialCards: (students: { full_name: string; login: string; password: string }[], title?: string) =>
    apiFile(`${CR}/students/cards.pdf`, { body: { students, title: title ?? null } }),
  requestLink: (identifier: string, group_id?: string | null) =>
    api<Student>(`${CR}/students/requests`, { method: "POST", body: { identifier, group_id } }),
  renameStudent: (id: string, name: PersonName) => api<Student>(`${CR}/students/${id}`, { method: "PATCH", body: { name } }),
  resetPassword: (id: string) => api<StudentCredentials>(`${CR}/students/${id}/reset-password`, { method: "POST" }),
  setStudentBilling: (id: string, paid: boolean) => api<Student>(`${CR}/students/${id}/billing`, { method: "PUT", body: { paid } }),
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

// ---- schedule ----

export type PersonRef = { id: string; full_name: string };

export type RescheduleRequest = {
  id: string;
  lesson_id: string;
  requested_by: string;
  requested_by_me: boolean;
  new_starts_at: string;
  new_ends_at: string;
  comment: string | null;
  status: string;
  created_at: string;
};

export type Lesson = {
  id: string;
  series_id: string | null;
  teacher: PersonRef;
  paid: boolean;
  trial: boolean;
  kind: "individual" | "group";
  group_id: string | null;
  title: string;
  subject: string | null;
  topic: string | null;
  exam_item_ids: string[];
  starts_at: string;
  ends_at: string;
  duration_min: number;
  status: "scheduled" | "cancelled";
  video_url: string | null;
  cancel_reason: string | null;
  participants: PersonRef[] | null;
  pending_reschedule: RescheduleRequest | null;
};

export type Repeat = { weekdays: number[]; interval_weeks: number; until?: string | null; count?: number | null };

export type LessonCreate = {
  kind: "individual" | "group";
  trial?: boolean;
  group_id?: string | null;
  student_id?: string | null;
  starts_at: string;
  duration_min: number;
  subject?: string | null;
  topic?: string | null;
  exam_item_ids?: string[];
  paid?: boolean | null;
  video_url?: string | null;
  repeat?: Repeat | null;
  timezone: string;
};

export type Scope = "this" | "following";

const SC = "/api/schedule";

export const schedule = {
  lessons: (from: Date, to: Date) =>
    api<Lesson[]>(`${SC}/lessons?from=${encodeURIComponent(from.toISOString())}&to=${encodeURIComponent(to.toISOString())}`),
  lesson: (id: string) => api<Lesson>(`${SC}/lessons/${id}`),
  create: (data: LessonCreate) => api<{ count: number; lessons: Lesson[] }>(`${SC}/lessons`, { method: "POST", body: data }),
  update: (
    id: string,
    data: { scope: Scope; starts_at?: string; duration_min?: number; subject?: string | null; topic?: string | null; exam_item_ids?: string[]; paid?: boolean; trial?: boolean; video_url?: string | null },
  ) => api<Lesson>(`${SC}/lessons/${id}`, { method: "PATCH", body: data }),
  cancel: (id: string, scope: Scope, reason?: string | null) =>
    api<Lesson>(`${SC}/lessons/${id}/cancel`, { method: "POST", body: { scope, reason } }),
  reschedule: (id: string, starts_at: string, comment?: string | null) =>
    api<Lesson>(`${SC}/lessons/${id}/reschedule`, { method: "POST", body: { starts_at, comment } }),
  requests: () => api<(RescheduleRequest & { lesson: Lesson })[]>(`${SC}/reschedule-requests`),
  acceptRequest: (id: string) => api<void>(`${SC}/reschedule-requests/${id}/accept`, { method: "POST" }),
  declineRequest: (id: string) => api<void>(`${SC}/reschedule-requests/${id}/decline`, { method: "POST" }),
  withdrawRequest: (id: string) => api<void>(`${SC}/reschedule-requests/${id}`, { method: "DELETE" }),
};

// ---- academic ----

export type AttendanceStatus = "present" | "absent" | "late" | "sick";

export type GradeType = { id: string; name: string; position: number; is_active: boolean };

export type Grade = {
  id: string;
  /** Урок; null — оценка за работу (колонка work_id). */
  lesson_id: string | null;
  work_id?: string | null;
  title?: string | null;
  student_id: string;
  value: number;
  grade_type_id: string;
  grade_type: string;
  comment: string;
  source: "manual" | "test";
  lesson_starts_at: string;
  created_at: string;
};

export type Stats = {
  average: number | null;
  grades_count: number;
  present: number;
  late: number;
  absent: number;
  sick: number;
  attendance_rate: number | null;
};

export type Journal = {
  title: string;
  lessons: { id: string; starts_at: string; subject: string | null; topic: string | null; started: boolean; ktp: string[] }[];
  /** Колонки оценок за тесты и ДЗ без привязки к уроку. */
  works: { id: string; title: string; at: string }[];
  students: { id: string; full_name: string; current: boolean; stats: Stats }[];
  grades: Grade[];
  attendance: { lesson_id: string; student_id: string; status: AttendanceStatus }[];
  stats: Stats;
};

export type MyGrades = {
  subjects: { subject: string; teacher_names: string[]; stats: Stats; grades: Grade[] }[];
  stats: Stats;
};

const AC = "/api/academic";

function period(from: Date, to: Date): string {
  return `from=${encodeURIComponent(from.toISOString())}&to=${encodeURIComponent(to.toISOString())}`;
}

// ---------- КТП ----------

export type PlanItem = { kind: "module" | "test" | "link" | "note"; ref_id?: string | null; title: string; url?: string | null };
export type PlanLessonInput = { topic: string; goals: string; class_items: PlanItem[]; home_items: PlanItem[]; exam_item_ids: string[] };
export type PlanLesson = PlanLessonInput & {
  id: string;
  position: number;
  planned_date: string | null;
  schedule_lesson_id: string | null;
  done: boolean;
};
export type TemplateStatus = "private" | "pending" | "published" | "rejected" | "removed";
export type PlanTemplateSummary = {
  id: string;
  title: string;
  subject: string | null;
  level: string | null;
  status: TemplateStatus;
  owner_id: string;
  author_name: string;
  lessons_count: number;
  updated_at: string;
};
export type PlanTemplate = PlanTemplateSummary & {
  description: string;
  review_comment: string | null;
  based_on_id: string | null;
  can_edit: boolean;
  lessons: (PlanLessonInput & { id: string })[];
};
export type PlanTemplateInput = { title: string; subject: string | null; level: string | null; description: string; lessons: PlanLessonInput[] };
export type PlanSummary = {
  id: string;
  title: string;
  subject: string | null;
  target_type: "student" | "group";
  target_id: string;
  target_title: string;
  lessons_count: number;
  done_count: number;
  next_topic: string | null;
  next_date: string | null;
  updated_at: string;
};
export type Plan = {
  id: string;
  title: string;
  subject: string | null;
  target_type: "student" | "group";
  target_id: string;
  target_title: string;
  template_id: string | null;
  start_date: string | null;
  lessons: PlanLesson[];
  slots: { id: string; starts_at: string; topic: string | null }[];
  updated_at: string;
};
export type LessonKtp = { plan_id: string; plan_title: string; lesson: PlanLesson };

// Пояс пользователя из профиля (lib/dates) — по нему сервер считает дни и недели.
const tzParam = () => `tz=${encodeURIComponent(timezone())}`;

export const planning = {
  templates: (scope: "mine" | "public", q = "") =>
    api<PlanTemplateSummary[]>(`${AC}/plan-templates?scope=${scope}${q ? `&q=${encodeURIComponent(q)}` : ""}`),
  template: (id: string) => api<PlanTemplate>(`${AC}/plan-templates/${id}`),
  createTemplate: (data: PlanTemplateInput) => api<PlanTemplate>(`${AC}/plan-templates`, { method: "POST", body: data }),
  updateTemplate: (id: string, data: PlanTemplateInput) => api<PlanTemplate>(`${AC}/plan-templates/${id}`, { method: "PUT", body: data }),
  deleteTemplate: (id: string) => api<void>(`${AC}/plan-templates/${id}`, { method: "DELETE" }),
  copyTemplate: (id: string) => api<PlanTemplate>(`${AC}/plan-templates/${id}/copy`, { method: "POST" }),
  submitTemplate: (id: string) => api<PlanTemplate>(`${AC}/plan-templates/${id}/submit`, { method: "POST" }),
  unpublishTemplate: (id: string) => api<PlanTemplate>(`${AC}/plan-templates/${id}/unpublish`, { method: "POST" }),

  plans: (targetId?: string) => api<PlanSummary[]>(`${AC}/plans${targetId ? `?target_id=${targetId}` : ""}`),
  plan: (id: string) => api<Plan>(`${AC}/plans/${id}`),
  createPlan: (data: {
    target_type: "student" | "group";
    target_id: string;
    title?: string | null;
    subject?: string | null;
    template_id?: string | null;
    start_date?: string | null;
    distribute?: boolean;
  }) => api<Plan>(`${AC}/plans?${tzParam()}`, { method: "POST", body: data }),
  updatePlan: (id: string, data: { title?: string; subject?: string | null; start_date?: string | null }) =>
    api<Plan>(`${AC}/plans/${id}`, { method: "PATCH", body: data }),
  deletePlan: (id: string) => api<void>(`${AC}/plans/${id}`, { method: "DELETE" }),
  distribute: (id: string, fromDate?: string | null) =>
    api<{ placed: number; left: number }>(`${AC}/plans/${id}/distribute`, { method: "POST", body: { from_date: fromDate || null, tz: timezone() } }),
  addLesson: (planId: string, data: PlanLessonInput, after?: string) =>
    api<PlanLesson>(`${AC}/plans/${planId}/lessons${after ? `?after=${after}` : ""}`, { method: "POST", body: data }),
  updateLesson: (planId: string, lessonId: string, data: Partial<PlanLessonInput> & { planned_date?: string | null; schedule_lesson_id?: string | null; done?: boolean }) =>
    api<PlanLesson>(`${AC}/plans/${planId}/lessons/${lessonId}?${tzParam()}`, { method: "PATCH", body: data }),
  deleteLesson: (planId: string, lessonId: string) => api<void>(`${AC}/plans/${planId}/lessons/${lessonId}`, { method: "DELETE" }),
  moveLesson: (planId: string, lessonId: string, to: number) =>
    api<Plan>(`${AC}/plans/${planId}/lessons/${lessonId}/move?to=${to}`, { method: "POST" }),
  saveAsTemplate: (planId: string) => api<PlanTemplate>(`${AC}/plans/${planId}/save-as-template`, { method: "POST" }),
  byLesson: (scheduleLessonId: string) => api<LessonKtp[]>(`${AC}/ktp/by-lesson/${scheduleLessonId}`),
};

export const academic = {
  gradeTypes: (all = false) => api<GradeType[]>(`${AC}/grade-types${all ? "?all=true" : ""}`),
  createGradeType: (name: string, position = 0) =>
    api<GradeType>(`${AC}/grade-types`, { method: "POST", body: { name, position } }),
  updateGradeType: (id: string, data: Partial<Pick<GradeType, "name" | "position" | "is_active">>) =>
    api<GradeType>(`${AC}/grade-types/${id}`, { method: "PATCH", body: data }),

  journal: (target: { group_id?: string; student_id?: string }, from: Date, to: Date) => {
    const t = target.group_id ? `group_id=${target.group_id}` : `student_id=${target.student_id}`;
    return api<Journal>(`${AC}/journal?${t}&${period(from, to)}`);
  },
  setAttendance: (lessonId: string, studentId: string, status: AttendanceStatus | null) =>
    api<void>(`${AC}/lessons/${lessonId}/attendance/${studentId}`, { method: "PUT", body: { status } }),
  allPresent: (lessonId: string) => api<void>(`${AC}/lessons/${lessonId}/attendance/all-present`, { method: "POST" }),
  addGrade: (lessonId: string, data: { student_id: string; value: number; grade_type_id: string; comment: string }) =>
    api<Grade>(`${AC}/lessons/${lessonId}/grades`, { method: "POST", body: data }),
  updateGrade: (id: string, data: { value?: number; grade_type_id?: string; comment?: string }) =>
    api<Grade>(`${AC}/grades/${id}`, { method: "PATCH", body: data }),
  deleteGrade: (id: string) => api<void>(`${AC}/grades/${id}`, { method: "DELETE" }),

  myGrades: (from: Date, to: Date) => api<MyGrades>(`${AC}/me/grades?${period(from, to)}`),
};

// ---- chat ----

export type Attachment = { id: string; filename: string; mime: string; size: number; url: string | null };

export type ChatMessage = {
  id: string;
  conversation_id: string;
  author_id: string;
  author_name: string;
  text: string;
  attachments: Attachment[];
  is_announcement: boolean;
  is_system: boolean; // служебное сообщение переговоров
  deleted: boolean;
  created_at: string;
};

export type Conversation = {
  id: string;
  kind: "direct" | "group" | "deal" | "support";
  title: string;
  group_id: string | null;
  other_user_id: string | null;
  my_role: string;
  can_write: boolean;
  unread: number;
  last_message: ChatMessage | null;
  pinned: ChatMessage | null;
  last_message_at: string | null;
};

export type Contact = { id: string; full_name: string; relation: string };

const CH = "/api/chat";

export const chat = {
  conversations: () => api<Conversation[]>(`${CH}/conversations`),
  conversation: (id: string) => api<Conversation>(`${CH}/conversations/${id}`),
  contacts: () => api<Contact[]>(`${CH}/contacts`),
  openDirect: (userId: string) => api<Conversation>(`${CH}/conversations/direct`, { method: "POST", body: { user_id: userId } }),
  messages: (id: string, before?: string) =>
    api<ChatMessage[]>(`${CH}/conversations/${id}/messages?limit=50${before ? `&before=${encodeURIComponent(before)}` : ""}`),
  send: (id: string, text: string, attachmentIds: string[] = [], announcement = false) =>
    api<ChatMessage>(`${CH}/conversations/${id}/messages`, {
      method: "POST",
      body: { text, attachment_ids: attachmentIds, announcement },
    }),
  attachment: (conversationId: string, fileId: string) =>
    api<Attachment>(`${CH}/conversations/${conversationId}/attachments/${fileId}`),
  read: (id: string) => api<void>(`${CH}/conversations/${id}/read`, { method: "POST", body: {} }),
  unpin: (id: string) => api<void>(`${CH}/conversations/${id}/pin`, { method: "DELETE" }),
  deleteMessage: (id: string) => api<void>(`${CH}/messages/${id}`, { method: "DELETE" }),
};

// ---- поддержка (chat) ----

export type TicketCategory = "account" | "lessons" | "tests" | "tutors" | "payments" | "bug" | "idea" | "other";
export type TicketStatus = "open" | "answered" | "closed";
export type SupportTicket = {
  id: string;
  category: TicketCategory;
  subject: string;
  status: TicketStatus;
  priority: boolean;
  requester_id: string;
  requester_name: string;
  requester_roles: string[];
  assignee_id: string | null;
  assignee_name: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  unread: number;
  last_text: string | null;
};

export const support = {
  create: (data: { category: TicketCategory; subject: string; text: string; attachment_ids: string[] }) =>
    api<SupportTicket>(`${CH}/support/tickets`, { method: "POST", body: data }),
  mine: () => api<SupportTicket[]>(`${CH}/support/tickets`),
  ticket: (id: string) => api<SupportTicket>(`${CH}/support/tickets/${id}`),
  queue: (status: TicketStatus, mine = false) => api<SupportTicket[]>(`${CH}/support/queue?status=${status}${mine ? "&mine=true" : ""}`),
  counts: () => api<{ open: number; mine_open: number }>(`${CH}/support/queue/counts`),
  assign: (id: string) => api<SupportTicket>(`${CH}/support/tickets/${id}/assign`, { method: "POST", body: {} }),
  close: (id: string) => api<SupportTicket>(`${CH}/support/tickets/${id}/close`, { method: "POST", body: {} }),
  reopen: (id: string) => api<SupportTicket>(`${CH}/support/tickets/${id}/reopen`, { method: "POST", body: {} }),
};

// ---- media ----

export type FilePurpose = "chat_attachment" | "answer" | "material" | "avatar" | "document" | "site" | "content";

/** Постоянная ссылка на картинку или файл внутри текста (назначение «content»): media каждый раз выдаёт свежую. */
export function contentFileUrl(fileId: string): string {
  return `/api/media/files/${fileId}/content`;
}

/** Перенести картинку с другого сайта к нам (вставили текст вместе с картинкой) — сервер скачает её сам. */
export function importImage(url: string): Promise<UploadedFile> {
  return api<UploadedFile>("/api/media/files/import", { method: "POST", body: { url } });
}

export function isContentFileUrl(href: string | undefined): boolean {
  return !!href && /^\/api\/media\/files\/[0-9a-f-]+\/content$/.test(href);
}

export type UploadedFile = { id: string; filename: string; mime: string; size: number; purpose: FilePurpose; url: string | null };

/** Загрузить файл в media (multipart). Возвращает id для прикрепления. */
export async function uploadFile(file: File, purpose: FilePurpose): Promise<UploadedFile> {
  const form = new FormData();
  form.append("file", file);
  form.append("purpose", purpose);
  const doUpload = async () => {
    const token = await currentAccessToken();
    return fetch("/api/media/files", {
      method: "POST",
      body: form,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      credentials: "same-origin",
    });
  };
  let resp: Response;
  try {
    resp = await doUpload();
    if (resp.status === 401 && (await refreshSession())) resp = await doUpload();
  } catch {
    throw new ApiError(0, "network_error", "Не удалось загрузить файл. Проверьте интернет.");
  }
  return parse<UploadedFile>(resp);
}

export function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} МБ`;
}

// ---- content (библиотека) ----

export type SubjectRef = { id: string; name: string; hidden?: boolean };

export type CourseStatus = "private" | "pending" | "published" | "rejected" | "removed";

export type CourseSummary = {
  id: string;
  title: string;
  description: string;
  subject: SubjectRef | null;
  owner_id: string;
  author_name: string;
  status: CourseStatus;
  review_comment: string | null;
  sections_count: number;
  materials_count: number;
  updated_at: string;
};

export type MaterialKind = "text" | "card" | "video" | "pdf" | "file" | "link" | "task";

export type MaterialBrief = { id: string; kind: MaterialKind; title: string; viewed: boolean; favorite: boolean };

export type CourseTree = CourseSummary & {
  sections: { id: string; title: string; description: string; modules: { id: string; title: string; description: string; materials: MaterialBrief[] }[] }[];
  can_edit: boolean;
  viewed_count: number;
};

export type Material = {
  id: string;
  module_id: string;
  course_id: string;
  kind: MaterialKind;
  title: string;
  body: string;
  url: string | null;
  file: { id: string; filename: string; mime: string; size: number | null; url: string | null } | null;
  task_id: string | null;
  position_sec: number;
  viewed: boolean;
  favorite: boolean;
};

export type ModuleContent = {
  id: string;
  title: string;
  description: string;
  course_id: string;
  course_title: string;
  section_title: string;
  materials: Material[];
  prev_module_id: string | null;
  next_module_id: string | null;
  can_edit: boolean;
};

export type ProgressReport = {
  materials: { id: string; title: string; kind: MaterialKind; module_title: string }[];
  students: { id: string; full_name: string; viewed: string[] }[];
};

const CT = "/api/content";

/** Публичные данные можно читать и без входа: токен передаётся, только если пользователь вошёл. */
function readOpts(authed: boolean) {
  return { auth: authed };
}

export const content = {
  subjects: () => api<SubjectRef[]>(`${CT}/subjects`, { auth: false }),
  allSubjects: () => api<SubjectRef[]>(`${CT}/subjects?all=true`),
  createSubject: (name: string) => api<SubjectRef>(`${CT}/subjects`, { method: "POST", body: { name } }),
  updateSubject: (id: string, data: { name?: string; hidden?: boolean }) =>
    api<SubjectRef>(`${CT}/subjects/${id}`, { method: "PATCH", body: data }),
  catalog: (params: { subject_id?: string; q?: string }) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]);
    return api<CourseSummary[]>(`${CT}/catalog?${qs}`, { auth: false });
  },
  myCourses: () => api<CourseSummary[]>(`${CT}/my/courses`),
  sharedCourses: () => api<CourseSummary[]>(`${CT}/shared/courses`),
  course: (id: string, authed: boolean) => api<CourseTree>(`${CT}/courses/${id}`, readOpts(authed)),
  module: (id: string, authed: boolean) => api<ModuleContent>(`${CT}/modules/${id}`, readOpts(authed)),

  createCourse: (data: { title: string; subject_id?: string | null; description?: string }) =>
    api<CourseTree>(`${CT}/courses`, { method: "POST", body: data }),
  addChild: (parentId: string, title: string) =>
    api<CourseTree>(`${CT}/nodes/${parentId}/children`, { method: "POST", body: { title } }),
  updateNode: (id: string, data: { title?: string; description?: string; subject_id?: string | null }) =>
    api<CourseTree>(`${CT}/nodes/${id}`, { method: "PATCH", body: data }),
  deleteNode: (id: string) => api<void>(`${CT}/nodes/${id}`, { method: "DELETE" }),
  moveNode: (id: string, direction: "up" | "down") =>
    api<CourseTree>(`${CT}/nodes/${id}/move`, { method: "POST", body: { direction } }),
  addMaterial: (
    moduleId: string,
    data: { kind: MaterialKind; title?: string; body?: string; file_id?: string | null; url?: string | null; task_id?: string | null },
  ) =>
    api<Material>(`${CT}/modules/${moduleId}/materials`, { method: "POST", body: data }),
  updateMaterial: (id: string, data: { title?: string; body?: string; url?: string }) =>
    api<Material>(`${CT}/materials/${id}`, { method: "PATCH", body: data }),
  deleteMaterial: (id: string) => api<void>(`${CT}/materials/${id}`, { method: "DELETE" }),
  moveMaterial: (id: string, direction: "up" | "down") =>
    api<void>(`${CT}/materials/${id}/move`, { method: "POST", body: { direction } }),
  submit: (id: string) => api<CourseTree>(`${CT}/courses/${id}/submit`, { method: "POST" }),
  unpublish: (id: string) => api<CourseTree>(`${CT}/courses/${id}/unpublish`, { method: "POST" }),

  saveProgress: (id: string, position_sec?: number) =>
    api<void>(`${CT}/materials/${id}/progress`, { method: "PUT", body: { position_sec } }),
  favorite: (id: string, on: boolean) => api<void>(`${CT}/materials/${id}/favorite`, { method: on ? "PUT" : "DELETE" }),
  favorites: () => api<Material[]>(`${CT}/favorites`),
  progress: (courseId: string, target: { group_id?: string; student_id?: string }) => {
    const t = target.group_id ? `group_id=${target.group_id}` : `student_id=${target.student_id}`;
    return api<ProgressReport>(`${CT}/courses/${courseId}/progress?${t}`);
  },
};

// ---- moderation ----

export type QueueItem = {
  id: string;
  kind: string;
  kind_label: string;
  ref_id: string;
  title: string;
  author_id: string;
  author_name: string;
  details: Record<string, unknown>;
  status: "pending" | "approved" | "rejected" | "withdrawn";
  comment: string | null;
  decided_at: string | null;
  created_at: string;
};

export const moderation = {
  queue: (status = "pending") => api<QueueItem[]>(`/api/moderation/queue?status=${status}`),
  decide: (id: string, decision: "approve" | "reject", comment?: string) =>
    api<QueueItem>(`/api/moderation/queue/${id}/decide`, { method: "POST", body: { decision, comment } }),
};

// ---- assessment (банк задач) ----

export type TaskType = "choice" | "short" | "long" | "code";
export type TaskStatus = CourseStatus;

export type TaskSummary = {
  id: string;
  /** Короткий номер задачи: «(100345) Задание 6». */
  number: number;
  title: string;
  type: TaskType;
  difficulty: 1 | 2 | 3;
  subject_id: string | null;
  subject_name: string | null;
  topic_id: string | null;
  topic_path: string[];
  exam_items: ExamLabel[];
  tags: string[];
  status: TaskStatus;
  owner_id: string;
  author_name: string;
  updated_at: string;
};

export type TaskFull = TaskSummary & {
  statement: string;
  explanation: string;
  theory_material_id: string | null;
  file_mode: "none" | "optional" | "required";
  options: { id: string; text: string; is_correct: boolean | null }[];
  answers: { mode: "exact" | "regex"; value: string }[] | null;
  starter_code: string;
  time_limit_s: number | null;
  memory_limit_mb: number | null;
  tests: { input: string; expected: string }[] | null;
  review_comment: string | null;
  can_edit: boolean;
  multiple: boolean;
};

export type TaskInput = {
  title: string;
  statement: string;
  type: TaskType;
  subject_id: string | null;
  subject_name: string | null;
  topic_id: string | null;
  exam_item_ids: string[];
  difficulty: number;
  tags: string[];
  explanation: string;
  file_mode: "none" | "optional" | "required";
  options: { text: string; is_correct: boolean }[];
  answers: { mode: "exact" | "regex"; value: string }[];
  starter_code: string;
  time_limit_s: number;
  memory_limit_mb: number;
  tests: { input: string; expected: string }[];
};

export type Submission = {
  id: string;
  task_id: string;
  student_id: string;
  context_type: "practice" | "assignment";
  context_id: string;
  answer: { option_ids?: string[]; text?: string; code?: string };
  files: Attachment[];
  status: "checking" | "correct" | "incorrect" | "error" | "pending_review" | "reviewed";
  score: number | null;
  failed_case: number | null;
  failure: "wrong_answer" | "runtime_error" | "time_limit" | "memory_limit" | null;
  teacher_comment: string | null;
  /** Когда проверил или изменил педагог. */
  reviewed_at?: string | null;
  created_at: string;
  checked_at: string | null;
  run_log: { number: number; status: string; time_ms: number; output: string; error: string }[] | null;
  task_title?: string | null;
  task_type?: TaskType | null;
};

export type ExamKind = "ege" | "oge";
export type ExamItem = { id: string; number: number; title: string };
export type Exam = { id: string; kind: ExamKind; subject_id: string; subject_name: string; title: string; items: ExamItem[] };
export type ExamLabel = { id: string; label: string; title: string };

export type ExamProgress = { attempted: number; solved: number; attempts: number; correct_attempts: number; last_at: string | null };
/** «Мои успехи» ученика: опыт, уровень, серия дней, достижения. */
export type GameAchievement = { code: string; title: string; text: string; icon: string; earned: boolean; current: number; target: number };
export type Game = {
  xp: number;
  level: { number: number; title: string; xp_from: number; xp_to: number };
  streak: number;
  best_streak: number;
  today_active: boolean;
  week: boolean[];
  solved: number;
  tests: number;
  achievements: GameAchievement[];
};

/** Этапы работы с заданием: материал (теория), практика (сами, не на оценку), контроль (проверка знаний). */
export type ExamStage = "theory" | "practice" | "control";
export type ExamBoardRow = {
  item_id: string;
  number: number;
  title: string;
  theory: boolean;
  practice: boolean;
  control: boolean;
  done: boolean;
  done_at: string | null;
  note: string | null;
  progress: ExamProgress;
  by_student: (ExamProgress & { student_id: string })[];
  tasks_in_bank: number;
};
export type ExamBoard = {
  exam: Exam;
  target_type: "student" | "group";
  target_id: string;
  can_edit: boolean;
  students: PersonRef[];
  rows: ExamBoardRow[];
};
export type ItemTaskProgress = {
  task_id: string;
  title: string;
  type: TaskType;
  attempts: number;
  solved: boolean;
  last_status: Submission["status"];
  last_at: string;
};

export type TimeMode = "none" | "total" | "per_task";
export type QuizSettings = { order_mode: "fixed" | "random"; shuffle_options: boolean; time_mode: TimeMode; time_limit_s: number | null };
export type QuizItemInput = { task_id: string; points: number; solution_file: boolean };
export type QuizInput = QuizSettings & { title: string; description: string; grade_level: number; items: QuizItemInput[] };
export type Quiz = QuizSettings & {
  id: string;
  title: string;
  description: string;
  /** Для какого класса (1–11); у старых тестов — null. */
  grade_level: number | null;
  items: { task_id: string; points: number; solution_file: boolean; task: TaskSummary }[];
  max_score: number;
  assignments_count: number;
  updated_at: string;
};
export type QuizSummary = {
  id: string;
  title: string;
  grade_level: number | null;
  tasks_count: number;
  max_score: number;
  time_mode: TimeMode;
  time_limit_s: number | null;
  assignments_count: number;
  updated_at: string;
};

export type AttemptBrief = {
  id: string;
  number: number;
  status: "in_progress" | "submitted";
  started_at: string;
  submitted_at: string | null;
  auto_submitted: boolean;
  finished_by_teacher?: boolean;
  /** Прокторинг: сервер видеосвязи видит показ экрана. */
  screen_sharing?: boolean;
  answered: number;
  /** Сколько заданий решено верно (после сдачи). */
  correct?: number | null;
  /** Таймер на весь тест / на текущее задание — когда выйдет время. */
  ends_at?: string | null;
  current_ends_at?: string | null;
  total: number;
  score: number | null;
  max_score: number;
  percent: number | null;
  grade: number | null;
  checked: boolean;
};
export type Assignment = {
  id: string;
  test_id: string;
  /** Название назначения — его видят ученики. */
  title: string;
  /** Название теста на момент назначения — для педагога. */
  test_title: string;
  /** Класс теста на момент назначения. */
  grade_level: number | null;
  description: string;
  kind: AssignmentKind;
  target_type: "student" | "group";
  target_id: string;
  target_title: string;
  teacher_id: string;
  teacher_name: string;
  lesson_id: string | null;
  opens_at: string | null;
  deadline: string | null;
  not_open_yet: boolean;
  overdue: boolean;
  closed: boolean;
  max_attempts: number | null;
  attempts_left: number | null;
  settings: QuizSettings;
  tasks_count: number;
  max_score: number;
  /** С какого процента 5, 4, 3. */
  grade_scale: GradeScaleStored;
  /** К заданиям прикладывают файлы с решением — итог после вашей проверки. */
  needs_review: boolean;
  grade_to_journal: boolean;
  grade_type_id: string | null;
  proctoring: boolean;
  created_at: string;
  students: { student_id: string; full_name: string; allowed_attempts: number; attempts: AttemptBrief[]; proctor_alerts: number }[];
  can_start: boolean;
  /** Время сервера — для точных таймеров. */
  server_time?: string;
};
export type AssignmentKind = "test" | "homework" | "live";
export type GradeScale = { five: number; four: number; three: number };
export type GradeScaleStored = { "5": number; "4": number; "3": number };
export type AssignInput = {
  kind: AssignmentKind;
  title?: string | null;
  opens_at?: string | null;
  max_attempts?: number | null;
  target_type: "student" | "group";
  target_id: string;
  lesson_id?: string | null;
  deadline?: string | null;
  grade_scale?: GradeScale;
  grade_to_journal?: boolean;
  grade_type_id?: string | null;
  proctoring?: boolean;
};
export type AttemptTask = {
  task: TaskFull;
  points: number;
  answer: Submission["answer"] | null;
  files: Attachment[];
  locked: boolean;
  /** Нужно прикрепить файл с решением. */
  solution_file: boolean;
  result: Submission | null;
  earned: number | null;
};
export type Attempt = {
  id: string;
  assignment_id: string;
  title: string;
  student_id: string;
  number: number;
  status: "in_progress" | "submitted";
  settings: QuizSettings;
  started_at: string;
  ends_at: string | null;
  current_index: number;
  current_ends_at: string | null;
  submitted_at: string | null;
  auto_submitted: boolean;
  score: number | null;
  max_score: number;
  percent: number | null;
  grade: number | null;
  checked: boolean;
  /** Работу проверяет педагог (файлы с решением). */
  needs_review: boolean;
  reviewed_at: string | null;
  /** Оценку поставил педагог вручную. */
  grade_override: number | null;
  grade_scale: GradeScaleStored;
  server_time: string;
  proctoring: boolean;
  finished_by_teacher?: boolean;
  /** Прокторинг: сервер видит показ экрана — ответы принимаются. */
  screen_ok?: boolean;
  tasks: AttemptTask[];
};

/** Узел рубрикатора: раздел (parent_id = null) или тема внутри раздела. */
export type Topic = {
  id: string;
  subject_id: string;
  subject_name: string;
  parent_id: string | null;
  title: string;
  position: number;
  count: number;
};

export type SolveView = { task: TaskFull; submissions: Submission[]; solved: boolean; explanation: string | null };

const AS = "/api/assessment";

export const assessment = {
  search: (params: Record<string, string | number | boolean | undefined>) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== "" && v !== false)
        .map(([k, v]) => [k, String(v)]),
    );
    return api<{ items: TaskSummary[]; total: number }>(`${AS}/tasks?${qs}`);
  },
  task: (id: string) => api<TaskFull>(`${AS}/tasks/${id}`),
  create: (data: TaskInput) => api<TaskFull>(`${AS}/tasks`, { method: "POST", body: data }),
  update: (id: string, data: TaskInput) => api<TaskFull>(`${AS}/tasks/${id}`, { method: "PUT", body: data }),
  remove: (id: string) => api<void>(`${AS}/tasks/${id}`, { method: "DELETE" }),
  copy: (id: string) => api<TaskFull>(`${AS}/tasks/${id}/copy`, { method: "POST" }),
  submitForReview: (id: string) => api<TaskFull>(`${AS}/tasks/${id}/submit`, { method: "POST" }),
  unpublish: (id: string) => api<TaskFull>(`${AS}/tasks/${id}/unpublish`, { method: "POST" }),

  solve: (id: string, contextId: string, contextType: "practice" | "assignment" = "practice") =>
    api<SolveView>(`${AS}/tasks/${id}/solve?context_type=${contextType}&context_id=${contextId}`),
  answer: (
    id: string,
    contextId: string,
    answer: Submission["answer"],
    fileIds: string[] = [],
    contextType: "practice" | "assignment" = "practice",
  ) =>
    api<Submission>(`${AS}/tasks/${id}/submissions`, {
      method: "POST",
      body: { context_type: contextType, context_id: contextId, answer, file_ids: fileIds },
    }),
  submission: (id: string) => api<Submission>(`${AS}/submissions/${id}`),
  history: (studentId: string, taskId?: string) =>
    api<Submission[]>(`${AS}/students/${studentId}/submissions${taskId ? `?task_id=${taskId}` : ""}`),
  moveTask: (id: string, topicId: string) => api<TaskFull>(`${AS}/tasks/${id}/topic`, { method: "POST", body: { topic_id: topicId } }),

  topics: (scope: "mine" | "public" = "public") => api<Topic[]>(`${AS}/topics?scope=${scope}`),
  createTopic: (data: { title: string; parent_id?: string | null; subject_id?: string; subject_name?: string }) =>
    api<Topic>(`${AS}/topics`, { method: "POST", body: data }),
  updateTopic: (id: string, data: { title?: string; position?: number }) =>
    api<Topic>(`${AS}/topics/${id}`, { method: "PATCH", body: data }),
  deleteTopic: (id: string) => api<void>(`${AS}/topics/${id}`, { method: "DELETE" }),

  exams: () => api<Exam[]>(`${AS}/exams`),
  createExam: (data: { kind: ExamKind; subject_id: string; subject_name: string; title: string }) =>
    api<Exam>(`${AS}/exams`, { method: "POST", body: data }),
  deleteExam: (id: string) => api<void>(`${AS}/exams/${id}`, { method: "DELETE" }),
  addExamItem: (examId: string, data: { number: number; title: string }) =>
    api<ExamItem>(`${AS}/exams/${examId}/items`, { method: "POST", body: data }),
  updateExamItem: (id: string, data: { number?: number; title?: string }) =>
    api<ExamItem>(`${AS}/exam-items/${id}`, { method: "PATCH", body: data }),
  deleteExamItem: (id: string) => api<void>(`${AS}/exam-items/${id}`, { method: "DELETE" }),
  examBoard: (examId: string, targetType: "student" | "group", targetId: string) =>
    api<ExamBoard>(`${AS}/exam-board?exam_id=${examId}&target_type=${targetType}&target_id=${targetId}`),
  myGame: (tz: string) => api<Game>(`${AS}/me/game?tz=${encodeURIComponent(tz)}`),
  /** Меняются только переданные поля. */
  setExamMark: (
    data: { target_type: "student" | "group"; target_id: string; item_id: string } & Partial<
      Record<ExamStage | "done", boolean> & { note: string }
    >,
  ) =>
    api<void>(`${AS}/exam-marks`, { method: "PUT", body: data }),
  examItemTasks: (studentId: string, itemId: string) =>
    api<ItemTaskProgress[]>(`${AS}/exam-board/tasks?student_id=${studentId}&item_id=${itemId}`),

  tests: () => api<QuizSummary[]>(`${AS}/tests`),
  test: (id: string) => api<Quiz>(`${AS}/tests/${id}`),
  createTest: (data: QuizInput) => api<Quiz>(`${AS}/tests`, { method: "POST", body: data }),
  updateTest: (id: string, data: QuizInput) => api<Quiz>(`${AS}/tests/${id}`, { method: "PUT", body: data }),
  deleteTest: (id: string) => api<void>(`${AS}/tests/${id}`, { method: "DELETE" }),
  assign: (testId: string, data: AssignInput) => api<Assignment>(`${AS}/tests/${testId}/assign`, { method: "POST", body: data }),
  assignments: (role: "teacher" | "student", params: { lesson_id?: string; target_id?: string } = {}) => {
    const qs = new URLSearchParams({ role, ...Object.fromEntries(Object.entries(params).filter(([, v]) => v)) });
    return api<Assignment[]>(`${AS}/assignments?${qs}`);
  },
  assignment: (id: string) => api<Assignment>(`${AS}/assignments/${id}`),
  reassign: (id: string, studentId: string, deadline?: string | null) => {
    const qs = new URLSearchParams({ student_id: studentId, ...(deadline ? { deadline } : {}) });
    return api<Assignment>(`${AS}/assignments/${id}/reassign?${qs}`, { method: "POST" });
  },
  closeAssignment: (id: string) => api<Assignment>(`${AS}/assignments/${id}/close`, { method: "POST" }),
  start: (assignmentId: string, consent = false) =>
    api<Attempt>(`${AS}/assignments/${assignmentId}/start`, { method: "POST", body: { consent } }),
  proctorEvent: (attemptId: string, kind: ProctorEventKind) =>
    api<void>(`${AS}/attempts/${attemptId}/proctor-events`, { method: "POST", body: { kind } }),
  proctorEvents: (attemptId: string) => api<{ kind: string; at: string }[]>(`${AS}/attempts/${attemptId}/proctor-events`),
  attempt: (id: string) => api<Attempt>(`${AS}/attempts/${id}`),
  attemptStatus: (id: string) =>
    api<{ status: "in_progress" | "submitted"; screen_ok: boolean; finished_by_teacher: boolean }>(`${AS}/attempts/${id}/status`),
  /** Педагог завершает работу ученика досрочно. */
  finishAttempt: (id: string) => api<Attempt>(`${AS}/attempts/${id}/finish`, { method: "POST" }),
  saveAnswer: (attemptId: string, taskId: string, answer: Submission["answer"], fileIds: string[] = []) =>
    api<Attempt>(`${AS}/attempts/${attemptId}/answers/${taskId}`, { method: "PUT", body: { answer, file_ids: fileIds } }),
  nextTask: (attemptId: string) => api<Attempt>(`${AS}/attempts/${attemptId}/next`, { method: "POST" }),
  submitAttempt: (attemptId: string) => api<Attempt>(`${AS}/attempts/${attemptId}/submit`, { method: "POST" }),
  /** Удалить назначенный тест целиком (попытки и оценки в журнале — тоже). */
  deleteAssignment: (id: string) => api<void>(`${AS}/assignments/${id}`, { method: "DELETE" }),
  /** Убрать работу у учеников: перечисленных и/или у всех несдавших. */
  removeStudents: (id: string, body: { student_ids?: string[]; not_submitted?: boolean }) =>
    api<{ removed: number; deleted: boolean }>(`${AS}/assignments/${id}/remove-students`, { method: "POST", body }),
  recheck: (submissionId: string) => api<Submission>(`${AS}/submissions/${submissionId}/recheck`, { method: "POST" }),
  /** Проверка работы педагогом: засчитать задания (только изменённые) и оценка (null — по критериям). */
  reviewAttempt: (attemptId: string, tasks: Record<string, boolean>, grade: number | null) =>
    api<Attempt>(`${AS}/attempts/${attemptId}/review`, { method: "POST", body: { tasks, grade } }),

  review: (id: string, score: number, comment: string) =>
    api<Submission>(`${AS}/submissions/${id}/review`, { method: "POST", body: { score, comment } }),
};

// ---------- видеосвязь ----------

export type VideoRoom = {
  lesson_id: string;
  title: string;
  is_teacher: boolean;
  status: "waiting" | "active" | "ended";
  started_at: string | null;
  lesson_ends_at: string;
  limit_ends_at: string | null;
  end_reason: string | null;
  screen_share: string[];
  recording: "starting" | "active" | "stopping" | null;
  max_participants: number;
  external_url: string | null;
};
export type VideoJoin = { url: string; token: string; room: VideoRoom };
export type LessonRecording = {
  id: string;
  lesson_id: string;
  title: string;
  status: "recording" | "ready" | "failed";
  error: string | null;
  started_at: string;
  ended_at: string | null;
  duration_s: number | null;
  size: number | null;
  expires_at: string | null;
  url: string | null;
  download_url: string | null;
  can_delete: boolean;
};

const VD = "/api/video";

export const video = {
  room: (lessonId: string) => api<VideoRoom>(`${VD}/rooms/${lessonId}`),
  join: (lessonId: string) => api<VideoJoin>(`${VD}/rooms/${lessonId}/join`, { method: "POST" }),
  screenShare: (lessonId: string, studentId: string, allowed: boolean) =>
    api<VideoRoom>(`${VD}/rooms/${lessonId}/screen-share`, { method: "POST", body: { student_id: studentId, allowed } }),
  recording: (lessonId: string, action: "start" | "stop") =>
    api<VideoRoom>(`${VD}/rooms/${lessonId}/recording?action=${action}`, { method: "POST" }),
  end: (lessonId: string) => api<VideoRoom>(`${VD}/rooms/${lessonId}/end`, { method: "POST" }),
  recordings: (lessonId?: string) => api<LessonRecording[]>(`${VD}/recordings${lessonId ? `?lesson_id=${lessonId}` : ""}`),
  deleteRecording: (id: string) => api<void>(`${VD}/recordings/${id}`, { method: "DELETE" }),
  proctorJoin: (assignmentId: string) => api<ProctorJoin>(`${VD}/proctoring/${assignmentId}/join`, { method: "POST" }),
  proctorRecordings: (assignmentId: string) => api<ProctorRecording[]>(`${VD}/proctoring/${assignmentId}/recordings`),
};

export type ProctorEventKind =
  | "screen_share_started"
  | "screen_share_stopped"
  | "tab_hidden"
  | "tab_visible"
  | "focus_lost"
  | "focus_back"
  | "camera_requested"
  | "camera_on"
  | "camera_off";
export type ProctorJoin = {
  url: string;
  token: string;
  role: "teacher" | "student";
  title: string;
  students: { id: string; full_name: string; attempt_id: string | null }[];
};
export type ProctorRecording = {
  id: string;
  student_id: string;
  student_name: string;
  attempt_id: string | null;
  status: "recording" | "ready" | "failed";
  started_at: string;
  duration_s: number | null;
  url: string | null;
  download_url: string | null;
  expires_at: string | null;
};

// ---------- маркетплейс ----------

export type TutorLevel = "1-4" | "5-9" | "10-11" | "student" | "adult";
export type TutorFormat = "individual" | "group";
export type Presence = { online: boolean; last_seen_at: string | null };
export type TutorCard = {
  user_id: string;
  full_name: string;
  photo_url: string | null;
  headline: string;
  subjects: SubjectRef[];
  levels: TutorLevel[];
  formats: TutorFormat[];
  price: number | null;
  experience_years: number | null;
  rating: number | null;
  reviews_count: number;
  education_verified: boolean;
  presence: Presence;
};
export type EducationDoc = {
  id: string;
  title: string;
  institution: string;
  year: number;
  status: "pending" | "approved" | "rejected" | null;
  comment: string | null;
  filename: string | null;
  file_url: string | null;
};
export type TutorPublic = TutorCard & {
  about: string;
  published: boolean;
  share_url: string;
  education: EducationDoc[];
  blocked_reason?: string | null;
};
export type MyTutorProfile = {
  profile: TutorPublic;
  photo_file_id: string | null;
  missing: string[];
  education: EducationDoc[];
  blocked_reason: string | null;
  /** Согласие на распространение ПД уже дано. */
  public_consent: boolean;
};
export type TutorProfileInput = {
  published: boolean;
  headline: string;
  about: string;
  photo_file_id: string | null;
  subject_ids: string[];
  levels: TutorLevel[];
  formats: TutorFormat[];
  price: number | null;
  experience_years: number | null;
  public_consent?: boolean;
};
export type TutorSearch = {
  subject_id?: string;
  level?: TutorLevel | "";
  format?: TutorFormat | "";
  price_min?: number | "";
  price_max?: number | "";
  min_rating?: number | "";
  verified?: boolean;
  q?: string;
  sort?: "rating" | "price_asc" | "price_desc" | "new";
  offset?: number;
};

const MK = "/api/marketplace";

export const marketplace = {
  myProfile: () => api<MyTutorProfile>(`${MK}/me/profile`),
  saveProfile: (data: TutorProfileInput) => api<MyTutorProfile>(`${MK}/me/profile`, { method: "PUT", body: data }),
  addEducation: (data: { title: string; institution: string; year: number; file_id: string }) =>
    api<MyTutorProfile>(`${MK}/me/education`, { method: "POST", body: data }),
  deleteEducation: (id: string) => api<MyTutorProfile>(`${MK}/me/education/${id}`, { method: "DELETE" }),
  search: (params: TutorSearch, authed: boolean) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== "" && v !== false)
        .map(([k, v]) => [k, String(v)]),
    );
    return api<{ items: TutorCard[]; total: number }>(`${MK}/tutors?${qs}`, readOpts(authed));
  },
  tutor: (id: string, authed: boolean) => api<TutorPublic>(`${MK}/tutors/${id}`, readOpts(authed)),
  /** Опубликованные профили по списку id (для редактора главной). */
  tutorsByIds: (ids: string[]) =>
    ids.length
      ? api<{ items: TutorCard[]; total: number }>(`${MK}/tutors?${new URLSearchParams(ids.map((id) => ["ids", id]))}&limit=50`, { auth: false })
      : Promise.resolve({ items: [] as TutorCard[], total: 0 }),
  educationForModerator: (id: string) => api<EducationDoc>(`${MK}/moderation/education/${id}`),

  competencies: (subjectId: string) => api<Competency[]>(`${MK}/competencies?subject_id=${subjectId}`, { auth: false }),
  createCompetency: (subjectId: string, title: string) =>
    api<Competency>(`${MK}/competencies`, { method: "POST", body: { subject_id: subjectId, title } }),
  updateCompetency: (id: string, data: { title?: string; position?: number }) =>
    api<Competency>(`${MK}/competencies/${id}`, { method: "PATCH", body: data }),
  deleteCompetency: (id: string) => api<void>(`${MK}/competencies/${id}`, { method: "DELETE" }),

  createRequest: (data: RequestInput) => api<LessonRequest>(`${MK}/requests`, { method: "POST", body: data }),
  myRequests: () => api<LessonRequest[]>(`${MK}/requests/mine`),
  closeRequest: (id: string) => api<LessonRequest>(`${MK}/requests/${id}/close`, { method: "POST" }),
  openRequests: (params: { subject_id?: string; all_subjects?: boolean } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v).map(([k, v]) => [k, String(v)]));
    return api<LessonRequest[]>(`${MK}/requests/open?${qs}`);
  },
  respond: (requestId: string, data: { price?: number | null; message: string }) =>
    api<Negotiation>(`${MK}/requests/${requestId}/respond`, { method: "POST", body: data }),
  myResponses: () => api<LessonRequest[]>(`${MK}/responses/mine`),
  negotiation: (id: string) => api<Negotiation>(`${MK}/responses/${id}`),
  proposePrice: (id: string, price: number) => api<Negotiation>(`${MK}/responses/${id}/price`, { method: "POST", body: { price } }),
  agree: (id: string) => api<Negotiation>(`${MK}/responses/${id}/agree`, { method: "POST" }),
  decline: (id: string) => api<Negotiation>(`${MK}/responses/${id}/decline`, { method: "POST" }),

  reviews: (tutorId: string, authed: boolean, offset = 0) =>
    api<ReviewsPage>(`${MK}/tutors/${tutorId}/reviews?offset=${offset}`, readOpts(authed)),
  saveReview: (tutorId: string, data: { rating: number; text: string }) =>
    api<MyReview>(`${MK}/tutors/${tutorId}/review`, { method: "PUT", body: data }),
  myReviews: () => api<MyReview[]>(`${MK}/reviews/mine`),
  deleteReview: (id: string) => api<void>(`${MK}/reviews/${id}`, { method: "DELETE" }),
  reviewsAboutMe: () => api<TutorReview[]>(`${MK}/me/reviews`),
  replyReview: (id: string, text: string) => api<TutorReview>(`${MK}/reviews/${id}/reply`, { method: "PUT", body: { text } }),
  disputeReview: (id: string, reason: string) =>
    api<TutorReview>(`${MK}/reviews/${id}/dispute`, { method: "POST", body: { reason } }),
  removeReview: (id: string, reason: string) =>
    api<void>(`${MK}/moderation/reviews/${id}`, { method: "DELETE", body: { reason } }),

  offers: (params: { subject_id?: string; level?: string; price_max?: number | "" }, authed: boolean) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]));
    return api<GroupOffer[]>(`${MK}/offers?${qs}`, readOpts(authed));
  },
  offer: (id: string, authed: boolean) => api<GroupOffer>(`${MK}/offers/${id}`, readOpts(authed)),
  tutorOffers: (tutorId: string, authed: boolean) => api<GroupOffer[]>(`${MK}/tutors/${tutorId}/offers`, readOpts(authed)),
  myOffers: () => api<GroupOffer[]>(`${MK}/offers/mine`),
  enrolledOffers: () => api<GroupOffer[]>(`${MK}/offers/enrolled`),
  createOffer: (data: OfferInput) => api<GroupOffer>(`${MK}/offers`, { method: "POST", body: data }),
  updateOffer: (id: string, data: OfferInput) => api<GroupOffer>(`${MK}/offers/${id}`, { method: "PUT", body: data }),
  extendOffer: (id: string, enrollUntil: string, startDate?: string) =>
    api<GroupOffer>(`${MK}/offers/${id}/extend`, { method: "POST", body: { enroll_until: enrollUntil, start_date: startDate ?? null } }),
  startOffer: (id: string) => api<GroupOffer>(`${MK}/offers/${id}/start`, { method: "POST" }),
  cancelOffer: (id: string) => api<GroupOffer>(`${MK}/offers/${id}/cancel`, { method: "POST" }),
  joinOffer: (id: string) => api<GroupOffer>(`${MK}/offers/${id}/join`, { method: "POST" }),
  leaveOffer: (id: string) => api<GroupOffer>(`${MK}/offers/${id}/leave`, { method: "POST" }),

  pendingTrials: () => api<TrialFollowup[]>(`${MK}/trials/pending`),
  answerTrial: (lessonId: string, decision: "continue" | "stop", comment: string) =>
    api<TrialFollowup>(`${MK}/trials/${lessonId}/answer`, { method: "POST", body: { decision, comment } }),
};

export type OfferSchedule = {
  weekdays: number[];
  time: string;
  duration_min: 30 | 45 | 60 | 90 | 120;
  start_date: string;
  lessons_count: number | null;
  timezone: string;
};
export type OfferStatus = "recruiting" | "underfilled" | "started" | "closed" | "cancelled";
export type GroupOffer = {
  id: string;
  tutor: { id: string; full_name: string; photo_url: string | null; rating: number | null; reviews_count: number };
  title: string;
  subject: SubjectRef;
  levels: TutorLevel[];
  description: string;
  program: string[];
  schedule: OfferSchedule;
  price: number;
  min_students: number;
  max_students: number;
  enroll_until: string;
  private: boolean;
  status: OfferStatus;
  enrolled_count: number;
  seats_left: number;
  joinable: boolean;
  enrolled: boolean;
  is_owner: boolean;
  share_url: string;
  students: { id: string; full_name: string; enrolled_at: string }[] | null;
  started_at: string | null;
  created_at: string;
};
export type OfferInput = {
  title: string;
  subject_id: string;
  levels: TutorLevel[];
  description: string;
  program: string[];
  schedule: OfferSchedule;
  price: number;
  min_students: number;
  max_students: number;
  enroll_until: string;
  private: boolean;
};
export type TrialFollowup = {
  lesson_id: string;
  tutor: { id: string; full_name: string; photo_url: string | null; rating: number | null; reviews_count: number };
  title: string;
  lesson_starts_at: string;
  status: "pending" | "continue" | "stop";
  comment: string;
  answered_at: string | null;
  reviewed: boolean;
};

export type ReviewStatus = "pending" | "approved" | "rejected" | "removed";
export type ReviewPublic = { id: string; student_name: string; rating: number; text: string; published_at: string; reply: string | null };
export type MyReview = {
  id: string;
  tutor_id: string;
  tutor_name: string;
  rating: number;
  text: string;
  status: ReviewStatus;
  comment: string | null;
  reply: string | null;
  updated_at: string;
};
export type TutorReview = ReviewPublic & {
  reply_text: string | null;
  reply_status: "pending" | "approved" | "rejected" | null;
  reply_comment: string | null;
  dispute_id: string | null;
  dispute_status: "open" | "upheld" | "dismissed" | null;
  dispute_comment: string | null;
};
export type ReviewsPage = {
  items: ReviewPublic[];
  total: number;
  rating: number | null;
  reviews_count: number;
  distribution: Record<string, number>;
  can_review: boolean;
  mine: MyReview | null;
};

export type Competency = { id: string; subject_id: string; title: string; position: number };
export type RequestGoal = "ege" | "oge" | "school" | "gaps" | "olympiad" | "other";
export type RequestSchedule = { weekdays: number[] };
export type RequestInput = {
  tutor_id?: string | null;
  subject_id: string;
  goal: RequestGoal;
  current_ids: string[];
  desired_ids: string[];
  schedule: RequestSchedule;
  price: number;
  duration_min: 30 | 45 | 60 | 90;
  comment: string;
};
export type PersonBrief = { id: string; full_name: string; photo_url: string | null; rating: number | null; reviews_count: number };
export type DealResponse = {
  id: string; // он же id чата переговоров
  request_id: string;
  tutor: PersonBrief;
  status: "active" | "agreed" | "closed";
  price: number;
  proposed_by: "student" | "tutor";
  message: string;
  agreed_at: string | null;
  created_at: string;
};
export type LessonRequest = {
  id: string;
  student: PersonBrief;
  tutor_id: string | null;
  direct: boolean;
  subject_id: string;
  subject_name: string;
  goal: RequestGoal;
  current: string[];
  desired: string[];
  schedule: RequestSchedule;
  price: number;
  duration_min: number;
  comment: string;
  status: "open" | "agreed" | "closed" | "expired";
  expires_at: string;
  closed_at: string | null;
  created_at: string;
  responses: DealResponse[];
};
export type Negotiation = { response: DealResponse; request: LessonRequest; role: "student" | "tutor"; can_agree: boolean };

// ---- billing (подписка педагога) ----

const BL = "/api/billing";

export type BillingPayment = {
  id: string;
  purpose: string;
  description: string;
  amount_rub: number;
  status: "pending" | "succeeded" | "canceled";
  recurring: boolean;
  confirmation_url: string | null;
  error: string | null;
  created_at: string;
  paid_at: string | null;
};
export type SubscriptionState = {
  plan: "free" | "basic";
  period_end: string | null;
  auto_renew: boolean;
  payment_method_title: string | null;
  price_rub: number;
  pending_payment: BillingPayment | null;
};

export const billing = {
  subscription: () => api<SubscriptionState>(`${BL}/subscription`),
  checkout: (autoRenew: boolean) =>
    api<BillingPayment>(`${BL}/subscription/checkout`, { method: "POST", body: { auto_renew: autoRenew, accept_offer: true } }),
  setAutoRenew: (enabled: boolean) => api<SubscriptionState>(`${BL}/subscription/auto-renew`, { method: "PUT", body: { enabled } }),
  forgetCard: () => api<SubscriptionState>(`${BL}/subscription/payment-method`, { method: "DELETE" }),
  payments: () => api<BillingPayment[]>(`${BL}/payments`),
  payment: (id: string) => api<BillingPayment>(`${BL}/payments/${id}`),
  /** Только для поддельного провайдера: тестовая страница оплаты сообщает результат. */
  fakeResult: (id: string, outcome: "success" | "cancel", cardLast4: string) =>
    api<BillingPayment>(`${BL}/fake-provider/payments/${id}`, { method: "POST", body: { outcome, card_last4: cardLast4 } }),
};

// ---- аналитика (academic) ----

export type AnalyticsPeriod = { from: string; to: string; subject?: string };
export type TrendPoint = { week: string; average: number | null; attendance_rate: number | null };
export type HeatDay = { day: string; marked: number; missed: number; rate: number };
export type GroupReport = {
  title: string;
  subject: string | null;
  period_from: string;
  period_to: string;
  extended: boolean;
  stats: Stats;
  students: { id: string; full_name: string; current: boolean; stats: Stats; delta: number | null; trend: TrendPoint[] | null }[];
  distribution: Record<string, number> | null;
  trend: TrendPoint[] | null;
  heatmap: HeatDay[] | null;
};
export type StudentReport = {
  full_name: string;
  period_from: string;
  period_to: string;
  extended: boolean;
  stats: Stats;
  subjects: { subject: string; stats: Stats; class_average: number | null }[];
  grades: { at: string; value: number; subject: string | null; grade_type: string; comment: string }[] | null;
  trend: TrendPoint[] | null;
};
export type Summary = {
  period_from: string;
  period_to: string;
  rows: { group_id: string | null; title: string; students: number; stats: Stats; below_three: number }[];
  total: Stats;
};

function periodQs(p: AnalyticsPeriod, extra: Record<string, string> = {}): string {
  const tz = timezone();
  return new URLSearchParams({ from: p.from, to: p.to, tz, ...(p.subject ? { subject: p.subject } : {}), ...extra }).toString();
}

export const analytics = {
  group: (groupId: string, p: AnalyticsPeriod) => api<GroupReport>(`${AC}/analytics/groups/${groupId}?${periodQs(p)}`),
  student: (studentId: string, p: AnalyticsPeriod) => api<StudentReport>(`${AC}/analytics/students/${studentId}?${periodQs(p)}`),
  summary: (p: AnalyticsPeriod) => api<Summary>(`${AC}/analytics/summary?${periodQs(p)}`),
  /** Выгрузка: path — "groups/<id>", "students/<id>" или "summary". */
  export: (path: string, p: AnalyticsPeriod, format: "pdf" | "xlsx") =>
    apiFile(`${AC}/analytics/${path}/export?${periodQs(p, { format })}`, { method: "GET" }),
};

// ---- админ-панель ----

export type AdminUser = PersonName & {
  id: string;
  full_name: string;
  email: string | null;
  login: string | null;
  phone: string | null;
  roles: string[];
  status: "active" | "pending_verification" | "banned" | "deleted";
  status_reason: string | null;
  two_factor_method: string | null;
  managed_by_teacher_id: string | null;
  email_verified: boolean;
  created_at: string;
  last_seen_at: string | null;
  deleted_at: string | null;
  restore_until: string | null;
  timezone: string;
};
export type UserStats = {
  total: number;
  by_role: Record<string, number>;
  by_status: Record<string, number>;
  dau: number;
  wau: number;
  mau: number;
  series: { day: string; active: number; registrations: number }[];
};
export type AuditRecord = { event_id: string; type: string; producer: string; actor_id: string | null; occurred_at: string; data: Record<string, unknown> };
export type AuditStats = {
  activity: { type: string; title: string; total: number; by_day: Record<string, number> }[];
  top_teachers: { actor_id: string; actions: number }[];
};
export type AdminPayment = BillingPayment & { user_id: string; provider: string };
export type BillingStats = {
  subscribers: number;
  auto_renew: number;
  ever_paid: number;
  revenue_rub: number;
  months: { month: string; revenue_rub: number; payments: number }[];
};

function qs(params: Record<string, string | number | undefined | null | string[]>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => q.append(k, x));
    else q.set(k, String(v));
  }
  return q.toString();
}

export type AdminContentKind = "course" | "task" | "template" | "offer" | "tutor";
const CONTENT_PATHS: Record<AdminContentKind, string> = {
  course: "/api/content/admin/courses",
  task: "/api/assessment/admin/tasks",
  template: "/api/academic/admin/plan-templates",
  offer: "/api/marketplace/admin/offers",
  tutor: "/api/marketplace/admin/tutors",
};

export const admin = {
  users: (p: { q?: string; role?: string; status?: string; ids?: string[]; limit?: number; offset?: number }) =>
    api<{ items: AdminUser[]; total: number }>(`${ID}/admin/users?${qs(p)}`),
  user: (id: string) => api<AdminUser>(`${ID}/admin/users/${id}`),
  editUser: (id: string, data: { name?: PersonName; email?: string; login?: string; timezone?: string }) =>
    api<AdminUser>(`${ID}/admin/users/${id}`, { method: "PATCH", body: data }),
  setRoles: (id: string, roles: string[]) => api<AdminUser>(`${ID}/admin/users/${id}/roles`, { method: "PUT", body: { roles } }),
  ban: (id: string, reason: string) => api<AdminUser>(`${ID}/admin/users/${id}/ban`, { method: "POST", body: { reason } }),
  unban: (id: string) => api<AdminUser>(`${ID}/admin/users/${id}/unban`, { method: "POST" }),
  remove: (id: string, reason: string) => api<AdminUser>(`${ID}/admin/users/${id}/delete`, { method: "POST", body: { reason } }),
  restore: (id: string) => api<AdminUser>(`${ID}/admin/users/${id}/restore`, { method: "POST" }),
  resetPassword: (id: string) => api<{ password: string }>(`${ID}/admin/users/${id}/reset-password`, { method: "POST" }),
  userStats: (days = 30) => api<UserStats>(`${ID}/admin/stats?days=${days}`),

  audit: (p: { type_prefix?: string; user_id?: string; actor_id?: string; before?: string; limit?: number }) =>
    api<AuditRecord[]>(`/api/audit/audit?${qs(p)}`),
  auditStats: (days = 30) => api<AuditStats>(`/api/audit/audit/stats?days=${days}`),

  settings: () => api<Record<string, number>>(`${BL}/admin/settings`),
  saveSettings: (values: Record<string, number>) => api<Record<string, number>>(`${BL}/admin/settings`, { method: "PUT", body: { values } }),
  payments: (p: { status?: string; user_id?: string; limit?: number; offset?: number }) => api<AdminPayment[]>(`${BL}/admin/payments?${qs(p)}`),
  billingStats: () => api<BillingStats>(`${BL}/admin/stats`),
  /** Снять любой контент с платформы без очереди модерации / вернуть. */
  removeContent: (kind: AdminContentKind, id: string, reason: string) =>
    api<unknown>(`${CONTENT_PATHS[kind]}/${id}/${kind === "tutor" ? "hide" : "remove"}`, { method: "POST", body: { reason } }),
  restoreContent: (kind: AdminContentKind, id: string) =>
    api<unknown>(`${CONTENT_PATHS[kind]}/${id}/${kind === "tutor" ? "unhide" : "restore"}`, { method: "POST" }),
  grant: (userId: string, days: number, reason: string) =>
    api<{ period_end: string }>(`${BL}/admin/subscriptions/${userId}/grant`, { method: "POST", body: { days, reason } }),
};

// ---- главная страница и новости (администратор) ----

export const site = {
  landing: () => api<LandingOut>(`${CT}/admin/site/landing`),
  saveLanding: (data: Landing) => api<LandingOut>(`${CT}/admin/site/landing`, { method: "PUT", body: data }),
  news: () => api<NewsSummary[]>(`${CT}/admin/site/news`),
  newsItem: (id: string) => api<NewsFull>(`${CT}/admin/site/news/${id}`),
  createNews: (data: NewsInput) => api<NewsFull>(`${CT}/admin/site/news`, { method: "POST", body: data }),
  updateNews: (id: string, data: NewsInput) => api<NewsFull>(`${CT}/admin/site/news/${id}`, { method: "PUT", body: data }),
  deleteNews: (id: string) => api<void>(`${CT}/admin/site/news/${id}`, { method: "DELETE" }),
};
export type NewsInput = {
  title: string;
  slug?: string | null;
  summary: string;
  body: string;
  cover_file_id: string | null;
  status: "draft" | "published";
};
