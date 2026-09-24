"use client";

import { useState } from "react";

import { Alert, EmptyState, Spinner } from "@/components/ui";
import { academic, type Stats } from "@/lib/api";
import { fmtDate } from "@/lib/dates";
import { fmtAverage, fmtRate, gradeTone } from "@/lib/format";
import { useLoad } from "@/lib/hooks";

type Period = "month" | "quarter" | "year";

const PERIODS: { value: Period; label: string; months: number }[] = [
  { value: "month", label: "Месяц", months: 1 },
  { value: "quarter", label: "3 месяца", months: 3 },
  { value: "year", label: "Год", months: 12 },
];

function StatLine({ stats }: { stats: Stats }) {
  const missed = stats.absent + stats.sick;
  return (
    <p className="text-sm text-fg-soft">
      Средний балл <b className="text-fg">{fmtAverage(stats.average)}</b> · посещаемость{" "}
      <b className="text-fg">{fmtRate(stats.attendance_rate)}</b>
      {missed > 0 && ` · пропусков ${missed}${stats.sick ? ` (по болезни ${stats.sick})` : ""}`}
    </p>
  );
}

export default function MyGradesPage() {
  const [period, setPeriod] = useState<Period>("month");
  const months = PERIODS.find((p) => p.value === period)!.months;
  const [range] = useState(() => new Date());
  const to = new Date(range.getFullYear(), range.getMonth(), range.getDate() + 1);
  const from = new Date(to.getFullYear(), to.getMonth() - months, to.getDate());
  const data = useLoad(() => academic.myGrades(from, to), [period]);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Оценки</h1>
        <div className="flex rounded-xl border border-line bg-muted p-1 text-sm" role="tablist">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              role="tab"
              aria-selected={period === p.value}
              onClick={() => setPeriod(p.value)}
              className={`rounded-lg px-3 py-1 font-medium ${period === p.value ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {data.error && <Alert>{data.error}</Alert>}
      {!data.data && !data.error && <Spinner />}
      {data.data && data.data.subjects.length === 0 && (
        <EmptyState title="За этот период оценок нет" text="Оценки от всех педагогов будут собираться здесь." />
      )}
      {data.data && data.data.subjects.length > 0 && (
        <>
          <div className="rounded-2xl border border-line bg-surface p-5">
            <h2 className="font-semibold">Всего за период</h2>
            <StatLine stats={data.data.stats} />
          </div>
          {data.data.subjects.map((s) => (
            <section key={s.subject} className="rounded-2xl border border-line bg-surface">
              <div className="border-b border-line px-5 py-4">
                <div className="flex items-baseline justify-between gap-3">
                  <h2 className="text-lg font-semibold">{s.subject}</h2>
                  <span className={`text-2xl font-bold ${s.stats.average ? gradeTone(Math.round(s.stats.average)) : "text-fg-soft"}`}>
                    {fmtAverage(s.stats.average)}
                  </span>
                </div>
                <p className="text-sm text-fg-soft">{s.teacher_names.join(", ")}</p>
                <StatLine stats={s.stats} />
              </div>
              {s.grades.length > 0 && (
                <ul className="divide-y divide-line">
                  {s.grades.map((g) => (
                    <li key={g.id} className="flex items-start gap-3 px-5 py-3">
                      <span className={`w-6 text-xl font-bold ${gradeTone(g.value)}`}>{g.value}</span>
                      <div className="min-w-0 flex-1 text-sm">
                        <p className="font-medium">{g.grade_type}</p>
                        <p className="text-fg-soft">{g.comment}</p>
                      </div>
                      <span className="shrink-0 text-xs text-fg-soft">{fmtDate(g.lesson_starts_at, { day: "numeric", month: "short" })}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </>
      )}
    </div>
  );
}
