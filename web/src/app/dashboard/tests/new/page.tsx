"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { useLoad } from "@/lib/hooks";
import { readImportedTasks } from "@/lib/imported-tasks";
import { TestEditor } from "@/components/test-editor";

export default function NewTestPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <Link href="/dashboard/tests" className="text-sm text-fg-soft hover:text-fg">
        ← Тесты
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">Новый тест</h1>
      <Suspense>
        <Editor />
      </Suspense>
    </div>
  );
}

/** ?course=&module= — новый тест со страницы модуля курса, сразу привязан к нему. */
function Editor() {
  const q = useSearchParams();
  const courseId = q.get("course");
  const moduleId = q.get("module");
  const imported = q.get("imported") === "1";
  const tasks = useLoad(async () => imported ? readImportedTasks() : [], [imported]);
  if (imported && !tasks.data) return <p role="status">Загружаем задачи…</p>;
  return <TestEditor initialTasks={imported ? tasks.data ?? [] : undefined} preset={courseId && moduleId ? { courseId, moduleId } : undefined} />;
}
