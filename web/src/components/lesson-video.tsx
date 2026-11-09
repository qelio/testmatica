"use client";

import Link from "next/link";
import { useState } from "react";

import { type Lesson, video } from "@/lib/api";
import { fmtDateTime } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

/** Вход во встроенную видеокомнату: педагогу — за 30 минут, ученику — за 15, до 30 минут после конца. */
export function JoinLessonButton({ lesson, isTeacher }: { lesson: Lesson; isTeacher: boolean }) {
  const [now] = useState(() => Date.now());
  const opens = new Date(lesson.starts_at).getTime() - (isTeacher ? 30 : 15) * 60_000;
  const closes = new Date(lesson.ends_at).getTime() + 30 * 60_000;
  if (lesson.status !== "scheduled" || now > closes) return null;
  if (now < opens) {
    return <p className="text-center text-sm text-fg-soft">Видеокомната откроется {fmtDateTime(new Date(opens))}</p>;
  }
  return (
    <Link href={`/room/${lesson.id}`} className="flex h-11 items-center justify-center rounded-xl bg-brand font-medium text-on-brand hover:bg-brand-strong">
      Войти в занятие
    </Link>
  );
}

function fmtDuration(s: number | null): string {
  if (!s) return "";
  const m = Math.floor(s / 60);
  return m ? `${m} мин ${s % 60} с` : `${s} с`;
}

/** Записи занятия: смотреть и скачать — педагогу и ученикам занятия. */
export function LessonRecordings({ lessonId }: { lessonId: string }) {
  const list = useLoad(() => video.recordings(lessonId), [lessonId]);
  const [playing, setPlaying] = useState<string | null>(null);
  const [error, setError] = useState<string>();
  if (!list.data?.length) return null;
  return (
    <div className="space-y-2 border-t border-line pt-3">
      <h3 className="text-sm font-medium">Записи занятия</h3>
      {error && <p className="text-sm text-danger">{error}</p>}
      <ul className="space-y-2">
        {list.data.map((r) => (
          <li key={r.id} className="space-y-1.5 text-sm">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="min-w-0 flex-1">
                {r.status === "recording"
                  ? "Идёт запись…"
                  : r.status === "failed"
                    ? `Запись не сохранилась${r.error?.includes("before pipeline") ? ": её остановили раньше, чем она успела начаться" : ""}`
                    : `Запись ${fmtDuration(r.duration_s)}`}
                {r.expires_at && <span className="text-fg-soft"> · хранится до {fmtDateTime(r.expires_at)}</span>}
              </span>
              {r.url && (
                <button className="text-brand-text hover:underline" onClick={() => setPlaying(playing === r.id ? null : r.id)}>
                  {playing === r.id ? "Скрыть" : "Смотреть"}
                </button>
              )}
              {r.download_url && (
                <a href={r.download_url} className="text-brand-text hover:underline">
                  Скачать
                </a>
              )}
              {r.can_delete && r.status !== "recording" && (
                <button
                  className="text-fg-soft hover:text-danger"
                  onClick={async () => {
                    if (!window.confirm("Удалить запись? Её не увидят и ученики.")) return;
                    try {
                      await video.deleteRecording(r.id);
                      list.reload();
                    } catch (e) {
                      setError(errorText(e));
                    }
                  }}
                >
                  Удалить
                </button>
              )}
            </div>
            {playing === r.id && r.url && <video src={r.url} controls className="w-full rounded-lg bg-black" />}
          </li>
        ))}
      </ul>
    </div>
  );
}
