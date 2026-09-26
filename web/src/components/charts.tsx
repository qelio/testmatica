"use client";

import type { HeatDay, TrendPoint } from "@/lib/api";
import { fmtAverage, fmtRate } from "@/lib/format";

// Простые графики на SVG — без сторонних библиотек. Цвета — из токенов (currentColor / классы).

const W = 640;
const H = 220;
const PAD = { l: 34, r: 40, t: 12, b: 28 };

function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "short" }).replace(".", "");
}

/** Динамика: средний балл по неделям (линия, шкала 1–5) и посещаемость (пунктир, 0–100%). */
export function TrendChart({ points }: { points: TrendPoint[] }) {
  if (points.length === 0) return <p className="text-sm text-fg-soft">За период нет данных.</p>;
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const x = (i: number) => PAD.l + (points.length === 1 ? iw / 2 : (i * iw) / (points.length - 1));
  const yAvg = (v: number) => PAD.t + ih - ((v - 1) / 4) * ih;
  const yRate = (v: number) => PAD.t + ih - v * ih;
  const avg = points.map((p, i) => (p.average !== null ? [x(i), yAvg(p.average)] : null));
  const rate = points.map((p, i) => (p.attendance_rate !== null ? [x(i), yRate(p.attendance_rate)] : null));
  const path = (pts: (number[] | null)[]) =>
    pts
      .filter((p): p is number[] => p !== null)
      .map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`)
      .join(" ");
  const step = Math.max(1, Math.ceil(points.length / 8));
  return (
    <figure className="space-y-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Динамика среднего балла и посещаемости по неделям">
        {[1, 2, 3, 4, 5].map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={yAvg(v)} y2={yAvg(v)} className="stroke-line" strokeWidth={1} />
            <text x={PAD.l - 8} y={yAvg(v) + 4} textAnchor="end" className="fill-fg-soft text-[11px]">
              {v}
            </text>
          </g>
        ))}
        {[0, 0.5, 1].map((v) => (
          <text key={v} x={W - PAD.r + 6} y={yRate(v) + 4} className="fill-fg-soft text-[10px]">
            {Math.round(v * 100)}%
          </text>
        ))}
        {points.map((p, i) =>
          i % step === 0 ? (
            <text key={p.week} x={x(i)} y={H - 8} textAnchor="middle" className="fill-fg-soft text-[10px]">
              {shortDate(p.week)}
            </text>
          ) : null,
        )}
        <path d={path(rate)} fill="none" className="stroke-ok" strokeWidth={2} strokeDasharray="5 4" />
        <path d={path(avg)} fill="none" className="stroke-brand" strokeWidth={2.5} strokeLinejoin="round" />
        {avg.map((p, i) =>
          p ? (
            <circle key={i} cx={p[0]} cy={p[1]} r={3.5} className="fill-brand">
              <title>{`${shortDate(points[i].week)}: средний ${fmtAverage(points[i].average)}, посещаемость ${fmtRate(points[i].attendance_rate)}`}</title>
            </circle>
          ) : null,
        )}
      </svg>
      <figcaption className="flex gap-4 text-xs text-fg-soft">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-5 bg-brand" /> средний балл
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0 w-5 border-t-2 border-dashed border-ok" /> посещаемость
        </span>
      </figcaption>
    </figure>
  );
}

/** Мини-график среднего по неделям — в строке ученика. */
export function Sparkline({ points }: { points: TrendPoint[] }) {
  const vals = points.filter((p) => p.average !== null);
  if (vals.length < 2) return <span className="text-xs text-fg-soft">—</span>;
  const w = 80;
  const h = 22;
  const d = vals
    .map((p, i) => `${i ? "L" : "M"}${((i * w) / (vals.length - 1)).toFixed(1)},${(h - 2 - ((p.average! - 1) / 4) * (h - 4)).toFixed(1)}`)
    .join(" ");
  const up = vals[vals.length - 1].average! >= vals[0].average!;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-label={up ? "растёт" : "снижается"}>
      <path d={d} fill="none" className={up ? "stroke-ok" : "stroke-danger"} strokeWidth={1.8} strokeLinejoin="round" />
    </svg>
  );
}

/** Сколько каких оценок. */
export function DistributionBars({ values }: { values: Record<string, number> }) {
  const top = Math.max(1, ...Object.values(values));
  const tone: Record<string, string> = { "5": "bg-ok", "4": "bg-ok/70", "3": "bg-tutor", "2": "bg-danger/80", "1": "bg-danger" };
  return (
    <ul className="space-y-1.5">
      {["5", "4", "3", "2", "1"].map((v) => (
        <li key={v} className="flex items-center gap-2 text-sm">
          <span className="w-3 font-semibold">{v}</span>
          <span className="h-4 flex-1 overflow-hidden rounded bg-muted">
            <span className={`block h-full rounded ${tone[v]}`} style={{ width: `${((values[v] ?? 0) / top) * 100}%` }} />
          </span>
          <span className="w-8 text-right text-fg-soft tabular-nums">{values[v] ?? 0}</span>
        </li>
      ))}
    </ul>
  );
}

const WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];

/** Тепловая карта пропусков по дням: недели — столбцы, дни недели — строки (ТЗ: «тепловая карта по дням»). */
export function Heatmap({ days, from, to }: { days: HeatDay[]; from: string; to: string }) {
  const byDay = new Map(days.map((d) => [d.day, d]));
  const start = new Date(`${from}T00:00:00`);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7)); // с понедельника
  const end = new Date(`${to}T00:00:00`);
  const weeks: Date[][] = [];
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 7)) {
    weeks.push(Array.from({ length: 7 }, (_, i) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + i)));
  }
  const key = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return (
    <div className="space-y-2">
      <div className="flex gap-1 overflow-x-auto pb-1">
        <div className="grid shrink-0 grid-rows-7 gap-1 pr-1 text-[10px] text-fg-soft">
          {WEEKDAYS.map((w) => (
            <span key={w} className="h-4 leading-4">
              {w}
            </span>
          ))}
        </div>
        {weeks.map((week) => (
          <div key={key(week[0])} className="grid shrink-0 grid-rows-7 gap-1">
            {week.map((d) => {
              const info = byDay.get(key(d));
              const inRange = d >= new Date(`${from}T00:00:00`) && d <= end;
              const label = info
                ? `${d.toLocaleDateString("ru-RU")}: пропусков ${info.missed} из ${info.marked} (${Math.round(info.rate * 100)}%)`
                : d.toLocaleDateString("ru-RU");
              return (
                <span
                  key={key(d)}
                  title={label}
                  className={`h-4 w-4 rounded-sm ${!inRange ? "opacity-0" : info ? (info.missed ? "bg-danger" : "bg-ok/60") : "bg-muted"}`}
                  style={info?.missed ? { opacity: 0.25 + 0.75 * info.rate } : undefined}
                />
              );
            })}
          </div>
        ))}
      </div>
      <p className="flex flex-wrap items-center gap-3 text-xs text-fg-soft">
        <span className="flex items-center gap-1">
          <span className="h-3 w-3 rounded-sm bg-muted" /> нет занятий
        </span>
        <span className="flex items-center gap-1">
          <span className="h-3 w-3 rounded-sm bg-ok/60" /> все пришли
        </span>
        <span className="flex items-center gap-1">
          <span className="h-3 w-3 rounded-sm bg-danger/40" />
          <span className="h-3 w-3 rounded-sm bg-danger" /> чем темнее, тем больше пропусков
        </span>
      </p>
    </div>
  );
}
