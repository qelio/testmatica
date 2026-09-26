"use client";

import Link from "next/link";

import { TestEditor } from "@/components/test-editor";

export default function NewTestPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <Link href="/dashboard/tests" className="text-sm text-fg-soft hover:text-fg">
        ← Тесты
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">Новый тест</h1>
      <TestEditor />
    </div>
  );
}
