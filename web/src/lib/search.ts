// Поиск в шапке кабинета (решение №67). Общего поиска на сервере нет: браузер обращается к публичным API сервисов.
// Короткие списки (свои ученики, классы, тесты) загружаются один раз и ищутся на месте, большие (банк, библиотека) — на сервере.

import {
  BookOpen,
  Boxes,
  ClipboardCheck,
  LayoutGrid,
  ListChecks,
  type LucideIcon,
  UserCog,
  UserRound,
  Users,
} from "lucide-react";

import { admin, assessment, classroom, content, type CourseSummary } from "@/lib/api";
import { pluralWord } from "@/lib/format";
import { navFor } from "@/lib/navigation";

export const MIN_QUERY = 2;
const LIMIT = 5;
const CACHE_MS = 60_000;

export type SearchHit = { id: string; title: string; sub: string; href: string; extra?: string };
export type SearchGroup = { title: string; icon: LucideIcon; hits: SearchHit[] };
export type SearchResult = { query: string; groups: SearchGroup[]; failed: "none" | "some" | "all" };

type Source = {
  title: string;
  icon: LucideIcon;
  local?: () => Promise<SearchHit[]>;
  remote?: (query: string) => Promise<SearchHit[]>;
};

/** Без учёта регистра и различия е/ё; длина строки не меняется, поэтому позиции годятся для подсветки. */
export function normalize(text: string): string {
  return text.toLowerCase().replace(/ё/g, "е");
}

function cached<T>(load: () => Promise<T>): () => Promise<T> {
  let at = 0;
  let value: Promise<T> | null = null;
  return () => {
    if (!value || Date.now() - at > CACHE_MS) {
      at = Date.now();
      value = load().catch((e) => {
        value = null; // ошибку не запоминаем: следующий поиск попробует снова
        throw e;
      });
    }
    return value;
  };
}

function courseHit(c: CourseSummary): SearchHit {
  return { id: c.id, title: c.title, sub: c.subject?.name ?? "Курс", href: `/dashboard/library/course/${c.id}` };
}

function sourcesFor(roles: string[]): Source[] {
  const teacher = roles.includes("teacher");
  const staff = roles.includes("moderator") || roles.includes("admin");
  const student = roles.includes("student");
  const sources: Source[] = [];

  if (roles.includes("admin")) {
    sources.push({
      title: "Пользователи",
      icon: UserCog,
      remote: async (q) =>
        (await admin.users({ q, limit: LIMIT })).items.map((u) => ({
          id: u.id,
          title: u.full_name,
          sub: u.email ?? u.login ?? "",
          href: `/dashboard/users/${u.id}`,
        })),
    });
  }

  if (teacher) {
    const groups = cached(() => classroom.groups());
    const students = cached(() => classroom.students());
    sources.push(
      {
        title: "Ученики",
        icon: UserRound,
        local: async () => {
          // Без названий классов ученик всё равно должен находиться.
          const [list, classes] = await Promise.all([students(), groups().catch(() => [])]);
          const titles = new Map(classes.map((g) => [g.id, g.title]));
          return list.map((s) => ({
            id: s.student_id,
            title: s.full_name,
            sub: ["Ученик", ...s.group_ids.flatMap((id) => titles.get(id) ?? [])].join(" · "),
            href: `/dashboard/students/${s.student_id}`,
            extra: s.login ?? "",
          }));
        },
      },
      {
        title: "Классы",
        icon: Users,
        local: async () =>
          (await groups()).map((g) => ({
            id: g.id,
            title: g.title,
            sub: `${g.student_count} ${pluralWord(g.student_count, "ученик", "ученика", "учеников")}`,
            href: `/dashboard/groups/${g.id}`,
            extra: g.subject ?? "",
          })),
      },
    );
  }

  if (teacher || staff) {
    const tests = cached(() => assessment.tests());
    sources.push(
      {
        title: "Тесты",
        icon: ListChecks,
        local: async () =>
          (await tests()).map((t) => ({
            id: t.id,
            title: t.title,
            sub: `Тест · ${t.tasks_count} ${pluralWord(t.tasks_count, "задание", "задания", "заданий")}`,
            href: `/dashboard/tests/${t.id}`,
            extra: t.subject_name ?? "",
          })),
      },
      {
        title: "Банк задач",
        icon: Boxes,
        remote: async (q) =>
          (await assessment.search({ q, limit: LIMIT })).items.map((t) => ({
            id: t.id,
            title: t.title,
            sub: [`Задача ${t.number}`, t.subject_name].filter(Boolean).join(" · "),
            href: `/dashboard/tasks/${t.id}`,
          })),
      },
    );
  }

  if (student) {
    const assignments = cached(() => assessment.assignments("student"));
    sources.push({
      title: "Мои работы",
      icon: ClipboardCheck,
      local: async () =>
        (await assignments()).map((a) => ({ id: a.id, title: a.title, sub: "Работа", href: `/dashboard/assignments/${a.id}` })),
    });
  }

  // Свои курсы — только у педагога; библиотека опубликованных курсов доступна всем.
  const courses = teacher ? cached(() => content.myCourses()) : null;
  sources.push({
    title: "Библиотека",
    icon: BookOpen,
    local: courses ? async () => (await courses()).map(courseHit) : undefined,
    remote: async (q) => (await content.catalog({ q })).slice(0, LIMIT).map(courseHit),
  });

  const seen = new Set<string>();
  const sections = navFor(roles)
    .flatMap((s) => s.items.map((item) => ({ item, section: s.title })))
    .filter(({ item }) => item.ready && !seen.has(item.href) && !!seen.add(item.href));
  sources.push({
    title: "Разделы",
    icon: LayoutGrid,
    local: async () => sections.map(({ item, section }) => ({ id: item.href, title: item.title, sub: section ?? "Раздел", href: item.href })),
  });

  return sources;
}

async function searchSource(source: Source, query: string): Promise<SearchHit[]> {
  const needle = normalize(query);
  // У библиотеки два источника: свои курсы могут быть ещё не опубликованы, поэтому в каталоге их нет.
  const [local, remote] = await Promise.all([source.local?.() ?? [], source.remote?.(query) ?? []]);
  const found = local.filter((hit) => normalize(`${hit.title} ${hit.extra ?? ""}`).includes(needle));
  const ids = new Set(found.map((hit) => hit.id));
  return [...found, ...remote.filter((hit) => !ids.has(hit.id))].slice(0, LIMIT);
}

/** Поисковик для ролей пользователя. warm — загрузить короткие списки заранее, чтобы первый поиск был быстрым. */
export function createSearcher(roles: string[]) {
  const sources = sourcesFor(roles);
  return {
    warm() {
      sources.forEach((s) => void s.local?.().catch(() => {}));
    },
    async search(query: string): Promise<SearchResult> {
      const settled = await Promise.allSettled(sources.map((s) => searchSource(s, query)));
      const groups = settled.flatMap((r, i) =>
        r.status === "fulfilled" && r.value.length ? [{ title: sources[i].title, icon: sources[i].icon, hits: r.value }] : [],
      );
      const errors = settled.filter((r) => r.status === "rejected").length;
      return { query, groups, failed: errors === 0 ? "none" : errors === settled.length ? "all" : "some" };
    },
  };
}

export function searchPlaceholder(roles: string[]): string {
  if (roles.includes("admin")) return "Поиск: пользователи, тесты, курсы";
  if (roles.includes("moderator")) return "Поиск: тесты, задачи, курсы";
  if (roles.includes("teacher")) return "Поиск: ученики, классы, тесты, курсы";
  return "Поиск: работы, курсы, разделы";
}
