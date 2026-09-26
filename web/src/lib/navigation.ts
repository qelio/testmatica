// Разделы сайдбара по ролям (ТЗ, раздел 2).
// ready: false — раздел появится на следующих этапах, пока показывается как «скоро».

export type NavItem = { title: string; href: string; ready: boolean; badge?: "chats" };

const DASHBOARD: NavItem = { title: "Дашборд", href: "/dashboard", ready: true };
// В ТЗ чаты не перечислены среди разделов, но без пункта меню до них не добраться.
const CHATS: NavItem = { title: "Сообщения", href: "/dashboard/chats", ready: true, badge: "chats" };
const soon = (title: string, href: string): NavItem => ({ title, href, ready: false });

export const NAV = {
  // Одно меню педагога: режимов «учитель/репетитор» нет — платно или бесплатно указывается у группы и ученика.
  teacher: [
    DASHBOARD,
    CHATS,
    { title: "Расписание", href: "/dashboard/schedule", ready: true },
    { title: "Классы, группы, ученики", href: "/dashboard/groups", ready: true },
    { title: "Журнал", href: "/dashboard/journal", ready: true },
    { title: "Планирование (КТП)", href: "/dashboard/planning", ready: true },
    { title: "Тесты", href: "/dashboard/tests", ready: true },
    { title: "Назначение тестов", href: "/dashboard/assignments", ready: true },
    { title: "Банк задач", href: "/dashboard/tasks", ready: true },
    { title: "Библиотека", href: "/dashboard/library", ready: true },
    soon("Финансы и баланс", "/dashboard/finance"),
    { title: "Профиль репетитора", href: "/dashboard/profile", ready: true },
    { title: "Заявки учеников", href: "/dashboard/requests", ready: true },
    soon("Поддержка", "/dashboard/support"),
  ],
  student: [
    DASHBOARD,
    CHATS,
    { title: "Мои педагоги", href: "/dashboard/teachers", ready: true },
    { title: "Расписание", href: "/dashboard/schedule", ready: true },
    { title: "Назначенные тесты", href: "/dashboard/assignments", ready: true },
    { title: "Оценки", href: "/dashboard/grades", ready: true },
    { title: "ЕГЭ и ОГЭ", href: "/dashboard/exams", ready: true },
    { title: "Библиотека", href: "/dashboard/library", ready: true },
    { title: "Найти репетитора", href: "/tutors", ready: true },
    { title: "Мои заявки", href: "/dashboard/requests", ready: true },
    soon("Баланс", "/dashboard/balance"),
    soon("Поддержка", "/dashboard/support"),
  ],
  staff: [
    DASHBOARD,
    CHATS, // споры по отзывам — чаты поддержки
    { title: "Очередь модерации", href: "/dashboard/moderation", ready: true },
    { title: "Банк задач", href: "/dashboard/tasks", ready: true },
    { title: "Библиотека", href: "/dashboard/library", ready: true },
    { title: "Типы оценок", href: "/dashboard/grade-types", ready: true },
    { title: "Предметы", href: "/dashboard/subjects", ready: true },
    { title: "Компетенции", href: "/dashboard/competencies", ready: true },
    soon("Пользователи", "/dashboard/users"),
    soon("Журнал аудита", "/dashboard/audit"),
  ],
} satisfies Record<string, NavItem[]>;

export function navFor(roles: string[]): NavItem[] {
  if (roles.includes("admin") || roles.includes("moderator")) return NAV.staff;
  if (roles.includes("teacher")) return NAV.teacher;
  return NAV.student;
}
