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
  Handshake,
  House,
  Inbox,
  LayoutDashboard,
  LifeBuoy,
  MonitorUp,
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

export type NavSection = { title: string | null; items: NavItem[] };

const TOP: NavSection = { title: null, items: [DASHBOARD, CHATS] };

/** Разделы меню по ролям, сгруппированные по смыслу (подписи групп — как в школьных системах). */
export const NAV = {
  // Одно меню педагога: режимов «учитель/репетитор» нет — платно или бесплатно указывается у группы и ученика.
  teacher: [
    TOP,
    {
      title: "Мой день",
      items: [
        { title: "Расписание", href: "/dashboard/schedule", icon: CalendarDays, ready: true },
        { title: "Показать на доске", href: "/dashboard/board", icon: MonitorUp, ready: true },
      ],
    },
    {
      title: "Ученики и коллеги",
      items: [
        { title: "Классы, группы, ученики", href: "/dashboard/groups", icon: Users, ready: true },
        { title: "Мои коллеги", href: "/dashboard/colleagues", icon: Handshake, ready: true },
        { title: "Журнал", href: "/dashboard/journal", icon: NotebookPen, ready: true },
        { title: "Аналитика", href: "/dashboard/analytics", icon: ChartLine, ready: true },
      ],
    },
    {
      title: "Учебный процесс",
      items: [
        { title: "Планирование (КТП)", href: "/dashboard/planning", icon: ClipboardList, ready: true },
        { title: "Тесты", href: "/dashboard/tests", icon: ListChecks, ready: true },
        { title: "Назначение тестов", href: "/dashboard/assignments", icon: ClipboardCheck, ready: true },
        { title: "Банк задач", href: "/dashboard/tasks", icon: Boxes, ready: true },
        { title: "Библиотека", href: "/dashboard/library", icon: BookOpen, ready: true },
      ],
    },
    {
      title: "Репетиторство",
      items: [
        { title: "Профиль репетитора", href: "/dashboard/profile", icon: UserRound, ready: true },
        { title: "Заявки учеников", href: "/dashboard/requests", icon: Inbox, ready: true },
        { title: "Наборы в группы", href: "/dashboard/offers", icon: UsersRound, ready: true },
      ],
    },
    {
      title: "Аккаунт",
      items: [
        { title: "Тариф", href: "/dashboard/subscription", icon: Sparkles, ready: true },
        soon("Финансы и баланс", "/dashboard/finance", Wallet),
        SUPPORT,
        ACCOUNT,
      ],
    },
  ],
  student: [
    TOP,
    {
      title: "Учёба",
      items: [
        { title: "Расписание", href: "/dashboard/schedule", icon: CalendarDays, ready: true },
        { title: "Назначенные тесты", href: "/dashboard/assignments", icon: ClipboardCheck, ready: true },
        { title: "Оценки", href: "/dashboard/grades", icon: Star, ready: true },
        { title: "ЕГЭ и ОГЭ", href: "/dashboard/exams", icon: Target, ready: true },
        { title: "Библиотека", href: "/dashboard/library", icon: BookOpen, ready: true },
      ],
    },
    {
      title: "Педагоги",
      items: [
        { title: "Мои педагоги", href: "/dashboard/teachers", icon: GraduationCap, ready: true },
        { title: "Найти репетитора", href: "/dashboard/tutors", icon: Search, ready: true },
        { title: "Группы", href: "/dashboard/find-groups", icon: UsersRound, ready: true },
        { title: "Мои заявки", href: "/dashboard/requests", icon: FileText, ready: true },
      ],
    },
    { title: "Аккаунт", items: [soon("Баланс", "/dashboard/balance", Wallet), SUPPORT, ACCOUNT] },
  ],
  staff: [
    { title: null, items: [DASHBOARD, CHATS] }, // споры по отзывам — чаты поддержки
    {
      title: "Модерация",
      items: [{ title: "Очередь модерации", href: "/dashboard/moderation", icon: ShieldCheck, ready: true }, SUPPORT_QUEUE],
    },
    {
      // Штатный редактор ведёт курсы библиотеки — и тесты к их модулям (решение №44).
      title: "Материалы",
      items: [
        { title: "Банк задач", href: "/dashboard/tasks", icon: Boxes, ready: true },
        { title: "Библиотека", href: "/dashboard/library", icon: BookOpen, ready: true },
        { title: "Тесты", href: "/dashboard/tests", icon: ListChecks, ready: true },
      ],
    },
    {
      title: "Справочники",
      items: [
        { title: "Типы оценок", href: "/dashboard/grade-types", icon: Tags, ready: true },
        { title: "Предметы", href: "/dashboard/subjects", icon: Shapes, ready: true },
        { title: "Компетенции", href: "/dashboard/competencies", icon: Lightbulb, ready: true },
      ],
    },
    { title: "Аккаунт", items: [ACCOUNT] },
  ],
  // Администратор — всё, что у модератора, и управление платформой (ТЗ, раздел 2).
  admin: [] as NavSection[],
} satisfies Record<string, NavSection[]>;

NAV.admin = [
  ...NAV.staff.slice(0, -1),
  {
    title: "Платформа",
    items: [
      { title: "Пользователи", href: "/dashboard/users", icon: UserCog, ready: true },
      { title: "Статистика платформы", href: "/dashboard/platform-stats", icon: ChartNoAxesCombined, ready: true },
      { title: "Журнал аудита", href: "/dashboard/audit", icon: ScrollText, ready: true },
      { title: "Главная страница", href: "/dashboard/site", icon: House, ready: true },
      { title: "Настройки платформы", href: "/dashboard/platform", icon: Settings, ready: true },
    ],
  },
  ...NAV.staff.slice(-1),
];

export function navFor(roles: string[]): NavSection[] {
  if (roles.includes("admin")) return NAV.admin;
  if (roles.includes("moderator")) return NAV.staff;
  if (roles.includes("teacher")) return NAV.teacher;
  return NAV.student;
}

