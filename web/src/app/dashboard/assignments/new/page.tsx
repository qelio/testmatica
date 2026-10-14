"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AssignForm } from "@/components/assign-form";
import { Spinner } from "@/components/ui";
import type { AssignmentKind } from "@/lib/api";

export default function NewAssignmentPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <Link href="/dashboard/assignments" className="text-sm text-fg-soft hover:text-fg">
        ← Назначение тестов
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">Назначить тест</h1>
      <Suspense fallback={<Spinner />}>
        <Form />
      </Suspense>
    </div>
  );
}

/** Параметры для предзаполнения: ?test=&kind=&target_type=&target=&lesson= (из редактора теста и КТП). */
function Form() {
  const router = useRouter();
  const q = useSearchParams();
  const kind = q.get("kind");
  const targetType = q.get("target_type");
  return (
    <AssignForm
      preset={{
        testId: q.get("test") ?? undefined,
        kind: kind === "test" || kind === "homework" || kind === "live" ? (kind as AssignmentKind) : undefined,
        targetType: targetType === "group" || targetType === "student" ? targetType : undefined,
        targetId: q.get("target") ?? undefined,
        lessonId: q.get("lesson") ?? undefined,
        moduleId: q.get("module") ?? undefined,
      }}
      onAssigned={(a) => router.push(`/dashboard/assignments/${a.id}`)}
    />
  );
}
