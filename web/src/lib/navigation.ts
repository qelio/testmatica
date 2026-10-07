// Разделы сайдбара по ролям (ТЗ, раздел 2).
// ready: false — раздел появится на следующих этапах, пока показывается как «скоро».

import type { LucideIcon } from "lucide-react";
import {
  BookOpen,
  ChartLine,
  ChartNoAxesCombined,
  CircleUserRound,
  Boxes,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  FileText,
  GraduationCap,
  House,
  Inbox,
  LayoutDashboard,
  LifeBuoy,
  Lightbulb,
  ListChecks,
  MessageSquare,
  NotebookPen,
  ScrollText,
  Search,
  Settings,
  Shapes,
  ShieldCheck,
  Sparkles,
  Star,
  Tags,
  Target,
  UserCog,
  UserRound,
  Users,
  UsersRound,
  Wallet,
} from "lucide-react";

export type NavItem = { title: string; href: string; icon: LucideIcon; ready: boolean; badge?: "chats" | "support" };

const DASHBOARD: NavItem = { title: "Дашборд", href: "/dashboard", icon: LayoutDashboard, ready: true };
const ACCOUNT: NavItem = { title: "Личный кабинет", href: "/dashboard/account", icon: CircleUserRound, ready: true };
// В ТЗ чаты не перечислены среди разделов, но без пункта меню до них не добраться.
const CHATS: NavItem = { title: "Сообщения", href: "/dashboard/chats", icon: MessageSquare, ready: true, badge: "chats" };
// Пользователю — свои обращения (значок: есть непрочитанный ответ); поддержке — очередь (значок: ждут ответа).
const SUPPORT: NavItem = { title: "Поддержка", href: "/dashboard/support", icon: LifeBuoy, ready: true, badge: "support" };
const SUPPORT_QUEUE: NavItem = { title: "Обращения", href: "/dashboard/support", icon: LifeBuoy, ready: true, badge: "support" };
const soon = (title: string, href: string, icon: LucideIcon): NavItem => ({ title, href, icon, ready: false });

export const NAV = {
  // Одно меню педагога: режимов «учитель/репетитор» нет — платно или бесплатно указывается у группы и ученика.
  teacher: [
    DASHBOARD,
    CHATS,
    { title: "Расписание", href: "/dashboard/schedule", icon: CalendarDays, ready: true },
    { title: "Классы, группы, ученики", href: "/dashboard/groups", icon: Users, ready: true },
    { title: "Журнал", href: "/dashboard/journal", icon: NotebookPen, ready: true },
    { title: "Аналитика", href: "/dashboard/analytics", icon: ChartLine, ready: true },
    { title: "Планирование (КТП)", href: "/dashboard/planning", icon: ClipboardList, ready: true },
    { title: "Тесты", href: "/dashboard/tests", icon: ListChecks, ready: true },
    { title: "Назначение тестов", href: "/dashboard/assignments", icon: ClipboardCheck, ready: true },
    { title: "Банк задач", href: "/dashboard/tasks", icon: Boxes, ready: true },
    { title: "Библиотека", href: "/dashboard/library", icon: BookOpen, ready: true },
    soon("Финансы и баланс", "/dashboard/finance", Wallet),
    { title: "Тариф", href: "/dashboard/subscription", icon: Sparkles, ready: true },
    { title: "Профиль репетитора", href: "/dashboard/profile", icon: UserRound, ready: true },
    { title: "Заявки учеников", href: "/dashboard/requests", icon: Inbox, ready: true },
    { title: "Наборы в группы", href: "/dashboard/offers", icon: UsersRound, ready: true },
    SUPPORT,
    ACCOUNT,
  ],
  student: [
    DASHBOARD,
    CHATS,
    { title: "Мои педагоги", href: "/dashboard/teachers", icon: GraduationCap, ready: true },
    { title: "Расписание", href: "/dashboard/schedule", icon: CalendarDays, ready: true },
    { title: "Назначенные тесты", href: "/dashboard/assignments", icon: ClipboardCheck, ready: true },
    { title: "Оценки", href: "/dashboard/grades", icon: Star, ready: true },
    { title: "ЕГЭ и ОГЭ", href: "/dashboard/exams", icon: Target, ready: true },
    { title: "Библиотека", href: "/dashboard/library", icon: BookOpen, ready: true },
    { title: "Найти репетитора", href: "/dashboard/tutors", icon: Search, ready: true },
    { title: "Группы", href: "/dashboard/find-groups", icon: UsersRound, ready: true },
    { title: "Мои заявки", href: "/dashboard/requests", icon: FileText, ready: true },
    soon("Баланс", "/dashboard/balance", Wallet),
    SUPPORT,
    ACCOUNT,
  ],
  staff: [
    DASHBOARD,
    CHATS, // споры по отзывам — чаты поддержки
    { title: "Очередь модерации", href: "/dashboard/moderation", icon: ShieldCheck, ready: true },
    SUPPORT_QUEUE,
    { title: "Банк задач", href: "/dashboard/tasks", icon: Boxes, ready: true },
    { title: "Библиотека", href: "/dashboard/library", icon: BookOpen, ready: true },
    // Штатный редактор ведёт курсы библиотеки — и тесты к их модулям (решение №44).
    { title: "Тесты", href: "/dashboard/tests", icon: ListChecks, ready: true },
    { title: "Типы оценок", href: "/dashboard/grade-types", icon: Tags, ready: true },
    { title: "Предметы", href: "/dashboard/subjects", icon: Shapes, ready: true },
    { title: "Компетенции", href: "/dashboard/competencies", icon: Lightbulb, ready: true },
    ACCOUNT,
  ],
  // Администратор — всё, что у модератора, и управление платформой (ТЗ, раздел 2).
  admin: [] as NavItem[],
} satisfies Record<string, NavItem[]>;

NAV.admin = [
  ...NAV.staff,
  { title: "Пользователи", href: "/dashboard/users", icon: UserCog, ready: true },
  { title: "Статистика платформы", href: "/dashboard/platform-stats", icon: ChartNoAxesCombined, ready: true },
  { title: "Журнал аудита", href: "/dashboard/audit", icon: ScrollText, ready: true },
  { title: "Главная страница", href: "/dashboard/site", icon: House, ready: true },
  { title: "Настройки платформы", href: "/dashboard/platform", icon: Settings, ready: true },
];

export function navFor(roles: string[]): NavItem[] {
  if (roles.includes("admin")) return NAV.admin;
  if (roles.includes("moderator")) return NAV.staff;
  if (roles.includes("teacher")) return NAV.teacher;
  return NAV.student;
}
