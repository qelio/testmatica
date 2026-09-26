"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { AttemptView } from "@/components/attempt-view";
import { ProctorGuard, ProctorLog } from "@/components/proctor-guard";
import { Alert, Spinner } from "@/components/ui";
import { assessment } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/hooks";

export default function AttemptPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const attempt = useLoad(() => assessment.attempt(id), [id]);
  if (attempt.error) return <Alert>{attempt.error}</Alert>;
  if (!attempt.data) return <Spinner />;
  const teacher = attempt.data.student_id !== user?.id;
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Link href={`/dashboard/assignments/${attempt.data.assignment_id}`} className="text-sm text-fg-soft hover:text-fg">
        ← К заданию
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">
        {attempt.data.title}
        {attempt.data.number > 1 && <span className="text-fg-soft"> · попытка {attempt.data.number}</span>}
      </h1>
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
  );
}
