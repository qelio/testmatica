"use client";

import { useState } from "react";

import { Alert, Button, Modal } from "@/components/ui";
import { type BellSchedule, schedule } from "@/lib/api";
import { WEEKDAYS_SHORT } from "@/lib/dates";
import { errorText } from "@/lib/hooks";

type Period = { start: string; end: string };

/** Типовое школьное: уроки по 45 минут с 8:30, перемены 10 минут, после 2-го и 3-го — по 20. */
const SAMPLE: Period[] = [
  { start: "08:30", end: "09:15" },
  { start: "09:25", end: "10:10" },
  { start: "10:30", end: "11:15" },
  { start: "11:35", end: "12:20" },
  { start: "12:30", end: "13:15" },
  { start: "13:25", end: "14:10" },
  { start: "14:20", end: "15:05" },
];

function shift(time: string, minutes: number): string {
  const [h, m] = time.split(":").map(Number);
  const total = Math.min(23 * 60 + 59, h * 60 + m + minutes);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

/** Своё расписание звонков (решение №55): уроки по номерам и дни недели — в календаре полосами. */
export function BellsModal({ initial, onClose, onSaved }: { initial: BellSchedule; onClose: () => void; onSaved: (b: BellSchedule) => void }) {
  const [periods, setPeriods] = useState<Period[]>(initial.periods);
  const [weekdays, setWeekdays] = useState<number[]>(initial.weekdays);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const set = (i: number, patch: Partial<Period>) => setPeriods(periods.map((p, n) => (n === i ? { ...p, ...patch } : p)));
  const addPeriod = () => {
    const last = periods.at(-1);
    const start = last ? shift(last.end, 10) : "08:30";
    setPeriods([...periods, { start, end: shift(start, 45) }]);
  };

  async function save(next: BellSchedule) {
    setBusy(true);
    setError(undefined);
    try {
      onSaved(await schedule.saveBells(next));
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Расписание звонков">
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <p className="text-sm text-fg-soft">Уроки появятся в календаре светлыми полосами с номерами — видно только вам.</p>
        {!periods.length && (
          <button type="button" onClick={() => setPeriods(SAMPLE)} className="text-sm font-medium text-brand hover:underline">
            Заполнить типовым (8:30, уроки по 45 минут)
          </button>
        )}
        {periods.length > 0 && (
          <ol className="space-y-2">
            {periods.map((p, i) => (
              <li key={i} className="flex items-center gap-2">
                <span className="w-16 text-sm font-medium">{i + 1} урок</span>
                <input
                  type="time"
                  value={p.start}
                  onChange={(e) => set(i, { start: e.target.value })}
                  className="h-10 rounded-lg border border-line bg-surface px-2"
                  aria-label={`Начало ${i + 1} урока`}
                />
                <span className="text-fg-soft">—</span>
                <input
                  type="time"
                  value={p.end}
                  onChange={(e) => set(i, { end: e.target.value })}
                  className="h-10 rounded-lg border border-line bg-surface px-2"
                  aria-label={`Конец ${i + 1} урока`}
                />
                <button
                  type="button"
                  onClick={() => setPeriods(periods.filter((_, n) => n !== i))}
                  className="px-2 text-fg-soft hover:text-danger"
                  aria-label={`Убрать ${i + 1} урок`}
                >
                  ✕
                </button>
              </li>
            ))}
          </ol>
        )}
        {periods.length < 16 && (
          <button type="button" onClick={addPeriod} className="text-sm font-medium text-brand hover:underline">
            + Урок
          </button>
        )}
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">По каким дням</legend>
          <div className="flex flex-wrap gap-1.5">
            {WEEKDAYS_SHORT.map((label, d) => {
              const on = weekdays.includes(d);
              return (
                <button
                  key={d}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setWeekdays(on ? weekdays.filter((x) => x !== d) : [...weekdays, d].sort())}
                  className={`h-9 min-w-10 rounded-lg border px-2 text-sm ${on ? "border-brand bg-brand/10 text-brand" : "border-line text-fg-soft hover:text-fg"}`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </fieldset>
        <div className="flex flex-wrap justify-between gap-2">
          {initial.periods.length > 0 ? (
            <Button variant="ghost" className="text-danger" onClick={() => save({ periods: [], weekdays })} disabled={busy}>
              Убрать звонки
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              Отмена
            </Button>
            <Button onClick={() => save({ periods: periods.filter((p) => p.start && p.end), weekdays })} loading={busy}>
              Сохранить
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
