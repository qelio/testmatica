import type { CourseTheme } from "@/lib/api";

/** Оформления курсов и тестов для учеников (решение №42). Новая тема — сюда, стили — в globals.css (.tm-<тема>),
 *  значение — в схемах content и assessment и в функциях mcp. */
export const COURSE_THEMES: { id: CourseTheme; label: string; text: string }[] = [
  { id: "classic", label: "Классика", text: "Строгое оформление, как вся платформа" },
  { id: "comics", label: "Комикс", text: "Игровое: толстые контуры, яркие цвета, крупные заголовки — для 5–9 классов" },
];

export function themeLabel(theme: CourseTheme | undefined): string {
  return COURSE_THEMES.find((t) => t.id === theme)?.label ?? "Классика";
}
