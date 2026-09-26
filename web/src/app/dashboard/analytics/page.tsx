"use client";

import Link from "next/link";
import { useState } from "react";

import { DistributionBars, Heatmap, Sparkline, TrendChart } from "@/components/charts";
import { SubjectSelect } from "@/components/subject-select";
import { Alert, Badge, Button, Field, Select, Spinner } from "@/components/ui";
import { analytics, type AnalyticsPeriod, classroom, saveFile, type Stats } from "@/lib/api";
import { toDateInput } from "@/lib/dates";
import { fmtAverage, fmtRate, gradeTone } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

type Tab = "group" | "student" | "summary";

function presets(): { key: string; title: string; from: Date }[] {
  const now = new Date();
  const schoolYear = new Date(now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1, 8, 1);
  const ago = (days: number) => new Date(now.getTime() - days * 864e5);
  return [
    { key: "month", title: "Месяц", from: ago(30) },
    { key: "quarter", title: "3 месяца", from: ago(91) },
    { key: "half", title: "Полгода", from: ago(182) },
    { key: "year", title: "Учебный год", from: schoolYear },
  ];
}

/** Аналитика и отчёты педагога (ТЗ, раздел 8). */
export default function AnalyticsPage() {
  const [tab, setTab] = useState<Tab>("group");
  const [period, setPeriod] = useState<AnalyticsPeriod>(() => ({ from: toDateInput(presets()[1].from), to: toDateInput(new Date()) }));
  const tabs: [Tab, string][] = [
    ["group", "Класс / группа"],
    ["student", "Ученик"],
    ["summary", "Сводная ведомость"],
  ];
  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Аналитика</h1>
      <div className="flex rounded-xl border border-line bg-muted p-1 text-sm sm:w-fit" role="tablist">
        {tabs.map(([key, title]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`flex-1 rounded-lg px-4 py-1.5 font-medium whitespace-nowrap ${tab === key ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`}
          >
            {title}
          </button>
        ))}
      </div>
      <PeriodPicker value={period} onChange={setPeriod} />
      {tab === "group" && <GroupTab period={period} />}
      {tab === "student" && <StudentTab period={period} />}
      {tab === "summary" && <SummaryTab period={period} />}
    </div>
  );
}

function PeriodPicker({ value, onChange }: { value: AnalyticsPeriod; onChange: (p: AnalyticsPeriod) => void }) {
  const today = toDateInput(new Date());
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-wrap gap-1.5">
        {presets().map((p) => {
          const from = toDateInput(p.from);
          const on = value.from === from && value.to === today;
          return (
            <button
              key={p.key}
              type="button"
              aria-pressed={on}
              onClick={() => onChange({ ...value, from, to: today })}
              className={`rounded-lg border px-3 py-1.5 text-sm ${on ? "border-brand bg-brand/10 text-brand" : "border-line text-fg-soft hover:text-fg"}`}
            >
              {p.title}
            </button>
          );
        })}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Field label="С" type="date" value={value.from} max={value.to} onChange={(e) => e.target.value && onChange({ ...value, from: e.target.value })} />
        <Field label="По" type="date" value={value.to} min={value.from} onChange={(e) => e.target.value && onChange({ ...value, to: e.target.value })} />
      </div>
    </div>
  );
}

function StatCards({ s }: { s: Stats }) {
  const cards = [
    { title: "Средний балл", value: fmtAverage(s.average), tone: s.average !== null ? gradeTone(Math.round(s.average)) : "" },
    { title: "Посещаемость", value: fmtRate(s.attendance_rate), tone: "" },
    { title: "Оценок", value: String(s.grades_count), tone: "" },
    { title: "Пропусков", value: String(s.absent + s.sick), tone: s.absent + s.sick ? "text-danger" : "" },
    { title: "Опозданий", value: String(s.late), tone: "" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {cards.map((c) => (
        <div key={c.title} className="rounded-2xl border border-line bg-surface px-4 py-3">
          <p className="text-xs text-fg-soft">{c.title}</p>
          <p className={`text-2xl font-semibold tabular-nums ${c.tone}`}>{c.value}</p>
        </div>
      ))}
    </div>
  );
}

function Locked() {
  return (
    <div className="rounded-2xl border border-dashed border-brand/40 bg-brand/5 p-5 text-sm">
      <p className="font-medium">Динамика, сравнение с классом, тепловая карта пропусков, сводная ведомость и выгрузка в PDF/Excel</p>
      <p className="mt-1 text-fg-soft">
        Доступны на тарифе{" "}
        <Link href="/dashboard/subscription" className="text-brand hover:underline">
          «Базовый»
        </Link>
        . Средний балл и посещаемость — на любом тарифе.
      </p>
    </div>
  );
}

function ExportButtons({ path, period, enabled }: { path: string; period: AnalyticsPeriod; enabled: boolean }) {
  const [busy, setBusy] = useState<string>();
  const [error, setError] = useState<string>();
  if (!enabled) return null;
  async function run(format: "pdf" | "xlsx") {
    setBusy(format);
    setError(undefined);
    try {
      saveFile(await analytics.export(path, period, format), `Аналитика ${period.from} — ${period.to}.${format}`);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(undefined);
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="secondary" loading={busy === "pdf"} onClick={() => run("pdf")}>
        PDF
      </Button>
      <Button variant="secondary" loading={busy === "xlsx"} onClick={() => run("xlsx")}>
        Excel
      </Button>
      {error && <span className="text-sm text-danger">{error}</span>}
    </div>
  );
}

function Delta({ v }: { v: number | null }) {
  if (v === null) return <span className="text-fg-soft">—</span>;
  const text = `${v > 0 ? "+" : ""}${fmtAverage(v)}`;
  return <Badge tone={v >= 0 ? "ok" : "warn"}>{text}</Badge>;
}

// ---------- класс / группа ----------

function GroupTab({ period }: { period: AnalyticsPeriod }) {
  const groups = useLoad(() => classroom.groups(), []);
  const [groupId, setGroupId] = useState("");
  const [subject, setSubject] = useState("");
  const gid = groupId || groups.data?.[0]?.id || "";
  const p = { ...period, subject: subject || undefined };
  const report = useLoad(async () => (gid ? analytics.group(gid, p) : null), [gid, period.from, period.to, subject]);
  const r = report.data;

  if (groups.data && !groups.data.length) return <Alert kind="info">Создайте класс или группу — здесь появится аналитика по ним.</Alert>;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-56">
          <Select label="Класс / группа" value={gid} onChange={(e) => setGroupId(e.target.value)}>
            {groups.data?.map((g) => (
              <option key={g.id} value={g.id}>
                {g.title}
              </option>
            ))}
          </Select>
        </div>
        <div className="min-w-48">
          <SubjectSelect value={subject} onChange={setSubject} empty="Все предметы" />
        </div>
        <div className="ml-auto">{r && gid && <ExportButtons path={`groups/${gid}`} period={p} enabled={r.extended} />}</div>
      </div>
      {report.error && <Alert>{report.error}</Alert>}
      {!r ? (
        !report.error && <Spinner />
      ) : (
        <>
          <StatCards s={r.stats} />
          {!r.extended && <Locked />}
          {r.extended && (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <section className="rounded-2xl border border-line bg-surface p-5">
                <h2 className="mb-3 font-semibold">Динамика по неделям</h2>
                <TrendChart points={r.trend ?? []} />
              </section>
              <section className="rounded-2xl border border-line bg-surface p-5">
                <h2 className="mb-3 font-semibold">Оценки</h2>
                <DistributionBars values={r.distribution ?? {}} />
              </section>
            </div>
          )}
          <section className="overflow-x-auto rounded-2xl border border-line bg-surface">
            <table className="w-full min-w-[40rem] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-fg-soft">
                  <th className="px-4 py-2.5 font-medium">Ученик</th>
                  <th className="px-3 py-2.5 font-medium">Средний</th>
                  {r.extended && <th className="px-3 py-2.5 font-medium">От класса</th>}
                  {r.extended && <th className="px-3 py-2.5 font-medium">Динамика</th>}
                  <th className="px-3 py-2.5 font-medium">Оценок</th>
                  <th className="px-3 py-2.5 font-medium">Посещаемость</th>
                  <th className="px-3 py-2.5 font-medium">Пропуски</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {r.students.map((s) => (
                  <tr key={s.id} className={s.current ? "" : "text-fg-soft"}>
                    <td className="px-4 py-2">
                      {s.full_name}
                      {!s.current && <span className="ml-1 text-xs">(выбыл)</span>}
                    </td>
                    <td className={`px-3 py-2 font-semibold tabular-nums ${s.stats.average !== null ? gradeTone(Math.round(s.stats.average)) : ""}`}>
                      {fmtAverage(s.stats.average)}
                    </td>
                    {r.extended && (
                      <td className="px-3 py-2">
                        <Delta v={s.delta} />
                      </td>
                    )}
                    {r.extended && (
                      <td className="px-3 py-2">
                        <Sparkline points={s.trend ?? []} />
                      </td>
                    )}
                    <td className="px-3 py-2 tabular-nums">{s.stats.grades_count}</td>
                    <td className="px-3 py-2 tabular-nums">{fmtRate(s.stats.attendance_rate)}</td>
                    <td className={`px-3 py-2 tabular-nums ${s.stats.absent + s.stats.sick ? "text-danger" : ""}`}>{s.stats.absent + s.stats.sick}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          {r.extended && (
            <section className="rounded-2xl border border-line bg-surface p-5">
              <h2 className="mb-3 font-semibold">Пропуски по дням</h2>
              <Heatmap days={r.heatmap ?? []} from={r.period_from} to={r.period_to} />
            </section>
          )}
        </>
      )}
    </div>
  );
}

// ---------- ученик ----------

function StudentTab({ period }: { period: AnalyticsPeriod }) {
  const students = useLoad(() => classroom.students(), []);
  const [studentId, setStudentId] = useState("");
  const list = (students.data ?? []).filter((s) => s.status === "active");
  const sid = studentId || list[0]?.student_id || "";
  const report = useLoad(async () => (sid ? analytics.student(sid, period) : null), [sid, period.from, period.to]);
  const r = report.data;

  if (students.data && !list.length) return <Alert kind="info">Пока нет учеников.</Alert>;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-64">
          <Select label="Ученик" value={sid} onChange={(e) => setStudentId(e.target.value)}>
            {list.map((s) => (
              <option key={s.student_id} value={s.student_id}>
                {s.full_name}
              </option>
            ))}
          </Select>
        </div>
        <div className="ml-auto">{r && sid && <ExportButtons path={`students/${sid}`} period={period} enabled={r.extended} />}</div>
      </div>
      {report.error && <Alert>{report.error}</Alert>}
      {!r ? (
        !report.error && <Spinner />
      ) : (
        <>
          <StatCards s={r.stats} />
          {!r.extended && <Locked />}
          <section className="overflow-x-auto rounded-2xl border border-line bg-surface">
            <table className="w-full min-w-[32rem] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-fg-soft">
                  <th className="px-4 py-2.5 font-medium">Предмет</th>
                  <th className="px-3 py-2.5 font-medium">Средний</th>
                  {r.extended && <th className="px-3 py-2.5 font-medium">Средний по группе</th>}
                  <th className="px-3 py-2.5 font-medium">Оценок</th>
                  <th className="px-3 py-2.5 font-medium">Посещаемость</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {r.subjects.map((s) => (
                  <tr key={s.subject}>
                    <td className="px-4 py-2">{s.subject}</td>
                    <td className={`px-3 py-2 font-semibold tabular-nums ${s.stats.average !== null ? gradeTone(Math.round(s.stats.average)) : ""}`}>
                      {fmtAverage(s.stats.average)}
                    </td>
                    {r.extended && <td className="px-3 py-2 tabular-nums text-fg-soft">{fmtAverage(s.class_average)}</td>}
                    <td className="px-3 py-2 tabular-nums">{s.stats.grades_count}</td>
                    <td className="px-3 py-2 tabular-nums">{fmtRate(s.stats.attendance_rate)}</td>
                  </tr>
                ))}
                {!r.subjects.length && (
                  <tr>
                    <td colSpan={5} className="px-4 py-4 text-fg-soft">
                      За период нет оценок и отметок.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </section>
          {r.extended && r.trend && (
            <section className="rounded-2xl border border-line bg-surface p-5">
              <h2 className="mb-3 font-semibold">Динамика успеваемости</h2>
              <TrendChart points={r.trend} />
            </section>
          )}
          {r.extended && r.grades && r.grades.length > 0 && (
            <section className="rounded-2xl border border-line bg-surface p-5">
              <h2 className="mb-3 font-semibold">Оценки за период</h2>
              <ul className="divide-y divide-line text-sm">
                {[...r.grades].reverse().map((g, i) => (
                  <li key={i} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
                    <span className={`w-5 text-lg font-semibold ${gradeTone(g.value)}`}>{g.value}</span>
                    <span className="text-fg-soft tabular-nums">{new Date(g.at).toLocaleDateString("ru-RU")}</span>
                    <span>{g.subject ?? "—"}</span>
                    <span className="text-fg-soft">{g.grade_type}</span>
                    <span className="min-w-0 flex-1 truncate text-fg-soft">{g.comment}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}

// ---------- сводная ведомость ----------

function SummaryTab({ period }: { period: AnalyticsPeriod }) {
  const summary = useLoad(() => analytics.summary(period), [period.from, period.to]);
  if (summary.error) return summary.error.includes("Базовый") ? <Locked /> : <Alert>{summary.error}</Alert>;
  if (!summary.data) return <Spinner />;
  const r = summary.data;
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <ExportButtons path="summary" period={period} enabled />
      </div>
      <section className="overflow-x-auto rounded-2xl border border-line bg-surface">
        <table className="w-full min-w-[40rem] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-fg-soft">
              <th className="px-4 py-2.5 font-medium">Класс / группа</th>
              <th className="px-3 py-2.5 font-medium">Учеников</th>
              <th className="px-3 py-2.5 font-medium">Средний</th>
              <th className="px-3 py-2.5 font-medium">Оценок</th>
              <th className="px-3 py-2.5 font-medium">Посещаемость</th>
              <th className="px-3 py-2.5 font-medium">Пропуски</th>
              <th className="px-3 py-2.5 font-medium">Средний ниже 3</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {r.rows.map((row) => (
              <tr key={row.group_id ?? "solo"}>
                <td className="px-4 py-2 font-medium">{row.title}</td>
                <td className="px-3 py-2 tabular-nums">{row.students}</td>
                <td className={`px-3 py-2 font-semibold tabular-nums ${row.stats.average !== null ? gradeTone(Math.round(row.stats.average)) : ""}`}>
                  {fmtAverage(row.stats.average)}
                </td>
                <td className="px-3 py-2 tabular-nums">{row.stats.grades_count}</td>
                <td className="px-3 py-2 tabular-nums">{fmtRate(row.stats.attendance_rate)}</td>
                <td className="px-3 py-2 tabular-nums">{row.stats.absent + row.stats.sick}</td>
                <td className={`px-3 py-2 tabular-nums ${row.below_three ? "text-danger" : ""}`}>{row.below_three}</td>
              </tr>
            ))}
            <tr className="bg-muted font-medium">
              <td className="px-4 py-2">Всего</td>
              <td className="px-3 py-2" />
              <td className="px-3 py-2 tabular-nums">{fmtAverage(r.total.average)}</td>
              <td className="px-3 py-2 tabular-nums">{r.total.grades_count}</td>
              <td className="px-3 py-2 tabular-nums">{fmtRate(r.total.attendance_rate)}</td>
              <td className="px-3 py-2 tabular-nums">{r.total.absent + r.total.sick}</td>
              <td className="px-3 py-2" />
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  );
}
