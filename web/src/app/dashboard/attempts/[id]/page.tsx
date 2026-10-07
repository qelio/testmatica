"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { AttemptView } from "@/components/attempt-view";
import { ProctorGuard, ProctorLog } from "@/components/proctor-guard";
import { ThemeScope } from "@/components/theme-scope";
import { Alert, Spinner } from "@/components/ui";
import { assessment } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/hooks";
import { useRealtime } from "@/lib/realtime";

export default function AttemptPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const attempt = useLoad(() => assessment.attempt(id), [id]);
  // Педагог завершил работу или время вышло — сразу показываем итог.
  useRealtime((e) => {
    if (e.type === "assignment" && e.attempt_id === id && e.kind === "submitted") attempt.reload();
  });
  if (attempt.error) return <Alert>{attempt.error}</Alert>;
  if (!attempt.data) return <Spinner />;
  const teacher = attempt.data.student_id !== user?.id;
  // Оформление работы — из теста при назначении (решение №42); педагог видит работу так же, как ученик.
  return (
    <ThemeScope theme={attempt.data.settings.theme} className="mx-auto max-w-3xl">
    <div className="space-y-5">
      <Link href={`/dashboard/assignments/${attempt.data.assignment_id}`} className="text-sm text-fg-soft hover:text-fg">
        ← К заданию
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">
        {attempt.data.title}
        {attempt.data.number > 1 && <span className="text-fg-soft"> · попытка {attempt.data.number}</span>}
      </h1>
      {attempt.data.finished_by_teacher && (
        <Alert kind="info">
          {teacher ? "Вы завершили эту работу досрочно." : "Педагог завершил работу. Ответы, которые вы успели сохранить, отправлены на проверку."}
        </Alert>
      )}
      {attempt.data.proctoring && !teacher && attempt.data.status === "in_progress" ? (
        <ProctorGuard attemptId={attempt.data.id} assignmentId={attempt.data.assignment_id}>
          <AttemptView attempt={attempt.data} teacher={teacher} reload={attempt.reload} />
        </ProctorGuard>
      ) : (
        <>
          {attempt.data.proctoring && teacher && <ProctorLog attemptId={attempt.data.id} />}
          <AttemptView attempt={attempt.data} teacher={teacher} reload={attempt.reload} />
        </>
      )}
    </div>
    </ThemeScope>
  );
}
