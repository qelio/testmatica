"use client";

import { useRouter } from "next/navigation";

import { TaskEditor } from "@/components/task-editor";

export default function NewTaskPage() {
  const router = useRouter();
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Новая задача</h1>
      <div className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
        <TaskEditor onSaved={(t) => router.replace(`/dashboard/tasks/${t.id}`)} onCancel={() => router.back()} />
      </div>
    </div>
  );
}
