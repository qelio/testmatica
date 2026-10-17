"use client";

import { useState } from "react";

import { ATTEMPTS, GradeCriteria, When } from "@/components/assign-form";
import { TaskNumber } from "@/components/task-number";
import { Alert, Button, Field, Modal, Spinner } from "@/components/ui";
import { type Assignment, assessment, type AssignmentUpdate, type GradeScale } from "@/lib/api";
import { fromInputs, toDateInput, toTimeInput } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

/** Изменить выданную работу (решение №52): название, сроки, попытки, критерии, баллы за задания, «результаты после
 *  проверки». Баллы и критерии пересчитывают сданные работы; оценки, поставленные вручную, не меняются. */
export function AssignmentEdit({ a, onClose, onSaved }: { a: Assignment; onClose: () => void; onSaved: () => void }) {
  const parts = useLoad(() => assessment.assignmentParts(a.id), [a.id]);
  const [title, setTitle] = useState(a.title);
  const [openDate, setOpenDate] = useState(a.opens_at ? toDateInput(new Date(a.opens_at)) : "");
  const [openTime, setOpenTime] = useState(a.opens_at ? toTimeInput(new Date(a.opens_at)) : "08:00");
  const [closeDate, setCloseDate] = useState(a.deadline ? toDateInput(new Date(a.deadline)) : "");
  const [closeTime, setCloseTime] = useState(a.deadline ? toTimeInput(new Date(a.deadline)) : "20:00");
  const [attempts, setAttempts] = useState(a.max_attempts ? String(a.max_attempts) : "");
  const [scale, setScale] = useState<GradeScale>({ five: a.grade_scale["5"], four: a.grade_scale["4"], three: a.grade_scale["3"] });
  const [afterReview, setAfterReview] = useState(!!a.result_after_review);
  // Баллы по вариантам: null — ещё не меняли (берём из работы).
  const [points, setPoints] = useState<number[][] | null>(null);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const current = points ?? parts.data?.map((p) => p.items.map((i) => i.points)) ?? [];
  const fromTests = parts.data?.map((p, n) => p.items.map((i, k) => p.test_points[k] ?? current[n]?.[k] ?? i.points));
  const differsFromTests = !!fromTests && JSON.stringify(fromTests) !== JSON.stringify(current);
  const submitted = a.students.reduce((n, s) => n + s.attempts.filter((t) => t.status === "submitted").length, 0);
  const validScale = scale.five > scale.four && scale.four > scale.three;

  function setPoint(part: number, item: number, value: number) {
    setPoints(current.map((row, n) => (n === part ? row.map((v, k) => (k === item ? value : v)) : row)));
  }

  async function save() {
    setBusy(true);
    setError(undefined);
    const body: AssignmentUpdate = {
      title: title.trim() || a.title,
      opens_at: openDate ? fromInputs(openDate, openTime).toISOString() : null,
      deadline: closeDate ? fromInputs(closeDate, closeTime).toISOString() : null,
      max_attempts: attempts ? Number(attempts) : null,
      grade_scale: scale,
      result_after_review: afterReview,
      ...(points ? { points } : {}),
    };
    try {
      await assessment.updateAssignment(a.id, body);
      onSaved();
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Изменить параметры работы">
      <div className="space-y-5">
        {error && <Alert>{error}</Alert>}
        <Field label="Название для учеников" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
        <div className="grid gap-3 sm:grid-cols-2">
          <When label="Откроется (пусто — сразу)" date={openDate} time={openTime} onDate={setOpenDate} onTime={setOpenTime} />
          <When label="Закроется (пусто — без срока)" date={closeDate} time={closeTime} onDate={setCloseDate} onTime={setCloseTime} />
        </div>
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">Сколько раз можно пройти</legend>
          <div className="flex flex-wrap gap-1.5">
            {ATTEMPTS.map((o) => (
              <button
                key={o.value || "none"}
                type="button"
                aria-pressed={attempts === o.value}
                onClick={() => setAttempts(o.value)}
                className={`rounded-lg border px-3 py-1.5 text-sm ${attempts === o.value ? "border-brand bg-brand/10 text-brand" : "border-line text-fg-soft hover:text-fg"}`}
              >
                {o.title}
              </button>
            ))}
          </div>
        </fieldset>
        <GradeCriteria scale={scale} onChange={setScale} />
        <label className="flex items-start gap-3">
          <input type="checkbox" checked={afterReview} onChange={(e) => setAfterReview(e.target.checked)} className="mt-1 h-4 w-4 accent-brand" />
          <span className="text-sm">
            <span className="font-medium">Показать результаты только после моей проверки</span>
            <span className="block text-fg-soft">Ученик не видит «верно/неверно», разбор и оценку, пока вы не подтвердите проверку.</span>
          </span>
        </label>

        <section className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-medium">Баллы за задания</h3>
            {differsFromTests && (
              <button type="button" onClick={() => setPoints(fromTests!)} className="text-sm font-medium text-brand hover:underline">
                Взять баллы из теста
              </button>
            )}
          </div>
          {!parts.data ? (
            <Spinner />
          ) : (
            parts.data.map((p, n) => (
              <div key={p.test_id} className="space-y-1.5">
                {p.variant && (
                  <p className="text-xs font-medium text-fg-soft">
                    Вариант {p.variant}: {p.test_title} · всего баллов: {current[n]?.reduce((s, v) => s + v, 0)}
                  </p>
                )}
                <ol className="divide-y divide-line rounded-xl border border-line">
                  {p.items.map((i, k) => (
                    <li key={i.task_id} className="flex items-center gap-3 px-3 py-2 text-sm">
                      <span className="w-5 text-right text-fg-soft tabular-nums">{k + 1}</span>
                      <span className="min-w-0 flex-1 truncate">
                        <TaskNumber n={i.number} />
                        {i.title}
                      </span>
                      <input
                        type="number"
                        min={1}
                        max={100}
                        value={current[n]?.[k] ?? i.points}
                        onChange={(e) => setPoint(n, k, Math.min(100, Math.max(1, Number(e.target.value) || 1)))}
                        className="h-8 w-16 rounded-lg border border-line bg-surface px-2"
                        aria-label={`Баллы за задание ${k + 1}${p.variant ? `, вариант ${p.variant}` : ""}`}
                      />
                    </li>
                  ))}
                </ol>
              </div>
            ))
          )}
        </section>

        <p className="text-xs text-fg-soft">
          {submitted > 0
            ? `Сданные работы (${submitted}) пересчитаются по новым баллам и критериям, оценки в журнале обновятся. Оценки, которые вы поставили вручную, не изменятся. Состав заданий поменять нельзя.`
            : "Состав заданий поменять нельзя."}
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button onClick={save} loading={busy} disabled={!validScale}>
            Сохранить
          </Button>
        </div>
      </div>
    </Modal>
  );
}
