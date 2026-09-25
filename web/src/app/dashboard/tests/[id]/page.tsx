"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { TestEditor } from "@/components/test-editor";
import { Alert, Spinner } from "@/components/ui";
import { assessment } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export default function TestPage() {
  const { id } = useParams<{ id: string }>();
  const test = useLoad(() => assessment.test(id), [id]);
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <Link href="/dashboard/assignments?tab=tests" className="text-sm text-fg-soft hover:text-fg">
        ← Задания и тесты
      </Link>
      {test.error && <Alert>{test.error}</Alert>}
      {!test.data ? (
        !test.error && <Spinner />
      ) : (
        <>
          <h1 className="text-2xl font-semibold tracking-tight">{test.data.title}</h1>
          {test.data.assignments_count > 0 && (
            <p className="text-sm text-fg-soft">
              Тест уже выдавали ({test.data.assignments_count}). Изменения не затронут выданные работы — только новые.
            </p>
          )}
          <TestEditor key={test.data.id} test={test.data} />
        </>
      )}
    </div>
  );
}
