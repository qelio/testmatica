"use client";

import Link from "next/link";

import { Badge } from "@/components/ui";
import type { Assignment } from "@/lib/api";
import { attemptsText, gradeLevelLabel, KIND_LABELS, summary } from "@/lib/assignments";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/dates";

/** Карточка выданной работы для педагога: сводка по ученикам. inClass — в разделе класса (класс не повторяем). */
export function AssignmentCard({ a, inClass = false }: { a: Assignment; inClass?: boolean }) {
  const s = summary(a);
  const me = useAuth().user?.id;
  const live = a.kind === "live" && !a.closed && !a.not_open_yet;
  return (
    <Link href={`/dashboard/assignments/${a.id}`} className="block rounded-2xl border border-line bg-surface px-5 py-4 hover:border-brand/50">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1">
          <span className="font-medium">{a.title}</span>
          {a.test_title !== a.title && <span className="ml-2 text-sm text-fg-soft">по тесту «{a.test_title}»</span>}
        </span>
        {live && <Badge tone="brand">идёт сейчас</Badge>}
        <Badge tone={a.kind === "live" ? "brand" : "neutral"}>{KIND_LABELS[a.kind]}</Badge>
      </div>
      <p className="mt-1 text-sm text-fg-soft">
        {[
          inClass ? null : a.target_title,
          // Работа класса, которую назначил коллега или владелец класса (решение №61).
          me && a.teacher_id !== me ? `назначил(а) ${a.teacher_name}` : null,
          gradeLevelLabel(a.grade_level),
          a.not_open_yet && a.opens_at ? `откроется ${fmtDateTime(a.opens_at)}` : null,
          a.deadline ? `до ${fmtDateTime(a.deadline)}` : null,
          attemptsText(a),
          a.closed ? "завершён" : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <span>
          Сдали: <b>{s.submitted}</b> из {s.total}
        </span>
        {s.inProgress > 0 && <span className="text-brand-text">решают: {s.inProgress}</span>}
        {s.toReview > 0 && <span className="text-tutor">ждут проверки: {s.toReview}</span>}
        {s.avg !== null && <span className="text-fg-soft">средний результат {s.avg}%</span>}
      </p>
    </Link>
  );
}
