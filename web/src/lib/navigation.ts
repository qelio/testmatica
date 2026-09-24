// Разделы сайдбара по ролям и режимам педагога (ТЗ, раздел 2).
// ready: false — раздел появится на следующих этапах, пока показывается как «скоро».

export type NavItem = { title: string; href: string; ready: boolean };

const DASHBOARD: NavItem = { title: "Дашборд", href: "/dashboard", ready: true };
const soon = (title: string, href: string): NavItem => ({ title, href, ready: false });

export const NAV = {
  school: [
    DASHBOARD,
    { title: "Расписание", href: "/dashboard/schedule", ready: true },
    { title: "Мои классы/группы", href: "/dashboard/groups", ready: true },
    soon("Планирование (КТП)", "/dashboard/planning"),
    soon("Задания и тесты", "/dashboard/assignments"),
    soon("Библиотека", "/dashboard/library"),
    soon("Поддержка", "/dashboard/support"),
  ],
  tutor: [
    DASHBOARD,
    { title: "Расписание", href: "/dashboard/schedule", ready: true },
    { title: "Мои группы/ученики", href: "/dashboard/groups", ready: true },
    soon("Задания и тесты", "/dashboard/assignments"),
    soon("Библиотека", "/dashboard/library"),
    soon("Финансы и баланс", "/dashboard/finance"),
    soon("Профиль и поиск", "/dashboard/profile"),
    soon("Поддержка", "/dashboard/support"),
  ],
  student: [
    DASHBOARD,
    { title: "Мои педагоги", href: "/dashboard/teachers", ready: true },
    { title: "Расписание", href: "/dashboard/schedule", ready: true },
    soon("Задания", "/dashboard/assignments"),
    soon("Оценки", "/dashboard/grades"),
    soon("Библиотека", "/dashboard/library"),
    soon("Найти репетитора", "/dashboard/tutors"),
    soon("Баланс", "/dashboard/balance"),
    soon("Поддержка", "/dashboard/support"),
  ],
  staff: [
    DASHBOARD,
    soon("Очередь модерации", "/dashboard/moderation"),
    soon("Пользователи", "/dashboard/users"),
    soon("Журнал аудита", "/dashboard/audit"),
  ],
} satisfies Record<string, NavItem[]>;

export function navFor(roles: string[], teacherMode: string | null): NavItem[] {
  if (roles.includes("admin") || roles.includes("moderator")) return NAV.staff;
  if (roles.includes("teacher")) return teacherMode === "tutor" ? NAV.tutor : NAV.school;
  return NAV.student;
}
