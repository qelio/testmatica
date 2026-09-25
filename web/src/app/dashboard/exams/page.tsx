"use client";

import { ExamBoardView } from "@/components/exams";
import { Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";

/** Ученик: свой прогресс по заданиям ЕГЭ и ОГЭ и отметки педагогов. */
export default function MyExamsPage() {
  const { user } = useAuth();
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Подготовка к ЕГЭ и ОГЭ</h1>
        <p className="mt-1 text-sm text-fg-soft">
          Прогресс по каждому заданию экзамена — по задачам, которые вы решали в курсах и домашних заданиях. Галочки ставит педагог,
          когда задание пройдено.
        </p>
      </div>
      {user ? <ExamBoardView targetType="student" targetId={user.id} /> : <Spinner />}
    </div>
  );
}
