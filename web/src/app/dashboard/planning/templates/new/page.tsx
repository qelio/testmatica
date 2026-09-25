"use client";

import Link from "next/link";

import { TemplateEditor } from "@/components/template-editor";

export default function NewTemplatePage() {
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <Link href="/dashboard/planning?tab=templates" className="text-sm text-fg-soft hover:text-fg">
        ← Шаблоны КТП
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">Новый шаблон КТП</h1>
      <TemplateEditor />
    </div>
  );
}
