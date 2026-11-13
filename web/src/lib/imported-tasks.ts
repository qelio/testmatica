import type { TaskSummary } from "@/lib/api";

export const IMPORTED_TASKS_KEY = "testmatica:imported-tasks";

export type ImportedTask = Pick<TaskSummary, "id" | "title" | "type" | "subject_id" | "subject_name">;

export function readImportedTasks(): ImportedTask[] {
  try {
    const value = sessionStorage.getItem(IMPORTED_TASKS_KEY);
    const tasks = value ? JSON.parse(value) : [];
    return Array.isArray(tasks) ? tasks : [];
  } catch {
    return [];
  }
}
