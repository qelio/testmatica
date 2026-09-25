"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { TemplateEditor } from "@/components/template-editor";
import { Alert, Spinner } from "@/components/ui";
import { planning } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export default function TemplatePage() {
  const { id } = useParams<{ id: string }>();
  const t = useLoad(() => planning.template(id), [id]);
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <Link href="/dashboard/planning?tab=templates" className="text-sm text-fg-soft hover:text-fg">
        ← Шаблоны КТП
      </Link>
      {t.error && <Alert>{t.error}</Alert>}
      {!t.data ? (
        !t.error && <Spinner />
      ) : (
        <>
          <h1 className="text-2xl font-semibold tracking-tight">{t.data.title}</h1>
          <TemplateEditor key={`${t.data.id}-${t.data.updated_at}-${t.data.status}`} template={t.data} reload={t.reload} />
        </>
      )}
    </div>
  );
}
