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
  groups: (archived = false, mode?: "school" | "tutor") =>
    api<Group[]>(`${CR}/groups?archived=${archived}${mode ? `&mode=${mode}` : ""}`),
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
  mode: "school" | "tutor";
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
  group_id?: string | null;
  student_id?: string | null;
  starts_at: string;
  duration_min: number;
  subject?: string | null;
  topic?: string | null;
  exam_item_ids?: string[];
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
    data: { scope: Scope; starts_at?: string; duration_min?: number; subject?: string | null; topic?: string | null; exam_item_ids?: string[]; video_url?: string | null },
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
  lesson_id: string;
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
  lessons: { id: string; starts_at: string; subject: string | null; topic: string | null; started: boolean }[];
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
  deleted: boolean;
  created_at: string;
};

export type Conversation = {
  id: string;
  kind: "direct" | "group";
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

// ---- media ----

export type FilePurpose = "chat_attachment" | "answer" | "material" | "avatar";

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

export type SubjectRef = { id: string; name: string };

export type CourseStatus = "private" | "pending" | "published" | "rejected";

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
export type ExamBoardRow = {
  item_id: string;
  number: number;
  title: string;
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
  setExamMark: (data: { target_type: "student" | "group"; target_id: string; item_id: string; done: boolean; note: string }) =>
    api<void>(`${AS}/exam-marks`, { method: "PUT", body: data }),
  examItemTasks: (studentId: string, itemId: string) =>
    api<ItemTaskProgress[]>(`${AS}/exam-board/tasks?student_id=${studentId}&item_id=${itemId}`),

  review: (id: string, score: number, comment: string) =>
    api<Submission>(`${AS}/submissions/${id}/review`, { method: "POST", body: { score, comment } }),
};
