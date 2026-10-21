"use client";

import { PenLine } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui";
import { whiteboard } from "@/lib/api";
import { errorText, useLoad } from "@/lib/hooks";

const CLASS = "flex h-11 w-full items-center justify-center gap-2 rounded-xl border border-line font-medium hover:bg-muted";

/** Доска занятия (решение №60): педагог открывает (первый раз — создаётся), ученик — если педагог открыл ему доступ. */
export function LessonBoardButton({ lessonId, isTeacher }: { lessonId: string; isTeacher: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const shared = useLoad(() => (isTeacher ? Promise.resolve(null) : whiteboard.lessonBoard(lessonId).catch(() => null)), [lessonId, isTeacher]);
  if (!isTeacher) {
    return shared.data ? (
      <Link href={`/dashboard/boards/${shared.data.id}`} className={CLASS}>
        <PenLine size={18} /> Доска занятия
      </Link>
    ) : null;
  }
  return (
    <>
      {error && <Alert>{error}</Alert>}
      <button
        className={CLASS}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(undefined);
          try {
            const board = await whiteboard.openLesson(lessonId);
            router.push(`/dashboard/boards/${board.id}`);
          } catch (e) {
            setError(errorText(e));
            setBusy(false);
          }
        }}
      >
        <PenLine size={18} /> {busy ? "Открываю доску…" : "Доска занятия"}
      </button>
    </>
  );
}
