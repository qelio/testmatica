// Разделы сайдбара по ролям (ТЗ, раздел 2).
// ready: false — раздел появится на следующих этапах, пока показывается как «скоро».

import type { LucideIcon } from "lucide-react";
import {
  BookOpen,
  Boxes,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  FileText,
  GraduationCap,
  Inbox,
  LayoutDashboard,
  LifeBuoy,
  Lightbulb,
  ListChecks,
  MessageSquare,
  NotebookPen,
  ScrollText,
  Search,
  Shapes,
  ShieldCheck,
  Sparkles,
  Star,
  Tags,
  Target,
  UserCog,
  UserRound,
  Users,
  Wallet,
} from "lucide-react";

export type NavItem = { title: string; href: string; icon: LucideIcon; ready: boolean; badge?: "chats" };

const DASHBOARD: NavItem = { title: "Дашборд", href: "/dashboard", icon: LayoutDashboard, ready: true };
// В ТЗ чаты не перечислены среди разделов, но без пункта меню до них не добраться.
const CHATS: NavItem = { title: "Сообщения", href: "/dashboard/chats", icon: MessageSquare, ready: true, badge: "chats" };
const soon = (title: string, href: string, icon: LucideIcon): NavItem => ({ title, href, icon, ready: false });

export const NAV = {
  // Одно меню педагога: режимов «учитель/репетитор» нет — платно или бесплатно указывается у группы и ученика.
  teacher: [
    DASHBOARD,
    CHATS,
    { title: "Расписание", href: "/dashboard/schedule", icon: CalendarDays, ready: true },
    { title: "Классы, группы, ученики", href: "/dashboard/groups", icon: Users, ready: true },
    { title: "Журнал", href: "/dashboard/journal", icon: NotebookPen, ready: true },
    { title: "Планирование (КТП)", href: "/dashboard/planning", icon: ClipboardList, ready: true },
    { title: "Тесты", href: "/dashboard/tests", icon: ListChecks, ready: true },
    { title: "Назначение тестов", href: "/dashboard/assignments", icon: ClipboardCheck, ready: true },
    { title: "Банк задач", href: "/dashboard/tasks", icon: Boxes, ready: true },
    { title: "Библиотека", href: "/dashboard/library", icon: BookOpen, ready: true },
    soon("Финансы и баланс", "/dashboard/finance", Wallet),
    { title: "Тариф", href: "/dashboard/subscription", icon: Sparkles, ready: true },
    { title: "Профиль репетитора", href: "/dashboard/profile", icon: UserRound, ready: true },
    { title: "Заявки учеников", href: "/dashboard/requests", icon: Inbox, ready: true },
    soon("Поддержка", "/dashboard/support", LifeBuoy),
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
    { title: "Найти репетитора", href: "/tutors", icon: Search, ready: true },
    { title: "Мои заявки", href: "/dashboard/requests", icon: FileText, ready: true },
    soon("Баланс", "/dashboard/balance", Wallet),
    soon("Поддержка", "/dashboard/support", LifeBuoy),
  ],
  staff: [
    DASHBOARD,
    CHATS, // споры по отзывам — чаты поддержки
    { title: "Очередь модерации", href: "/dashboard/moderation", icon: ShieldCheck, ready: true },
    { title: "Банк задач", href: "/dashboard/tasks", icon: Boxes, ready: true },
    { title: "Библиотека", href: "/dashboard/library", icon: BookOpen, ready: true },
    { title: "Типы оценок", href: "/dashboard/grade-types", icon: Tags, ready: true },
    { title: "Предметы", href: "/dashboard/subjects", icon: Shapes, ready: true },
    { title: "Компетенции", href: "/dashboard/competencies", icon: Lightbulb, ready: true },
    soon("Пользователи", "/dashboard/users", UserCog),
    soon("Журнал аудита", "/dashboard/audit", ScrollText),
  ],
} satisfies Record<string, NavItem[]>;

export function navFor(roles: string[]): NavItem[] {
  if (roles.includes("admin") || roles.includes("moderator")) return NAV.staff;
  if (roles.includes("teacher")) return NAV.teacher;
  return NAV.student;
}
