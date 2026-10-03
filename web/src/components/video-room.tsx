"use client";

import "@livekit/components-styles";

import {
  LiveKitRoom,
  useDataChannel,
  useLocalParticipant,
  useParticipants,
} from "@livekit/components-react";
import { DisconnectReason } from "livekit-client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { RuConference } from "@/components/room-conference";
import { Alert, Button, Spinner } from "@/components/ui";
import { assessment, video, type VideoJoin, type VideoRoom } from "@/lib/api";
import { summary } from "@/lib/assignments";
import { fmtDateTime, fmtTime } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

const REACTIONS = ["👍", "👏", "😂", "🎉", "❓"];
const WARN_BEFORE_MS = 5 * 60_000;

function endMessage(
  room: VideoRoom | undefined,
  reason?: DisconnectReason,
): string {
  if (room?.end_reason === "time_limit")
    return "Время бесплатного занятия (40 минут) истекло.";
  if (room?.end_reason === "teacher") return "Педагог завершил занятие.";
  if (reason === DisconnectReason.DUPLICATE_IDENTITY)
    return "Вы вошли в занятие с другого устройства или вкладки.";
  if (reason === DisconnectReason.PARTICIPANT_REMOVED)
    return "Педагог отключил вас от занятия.";
  return "Вы вышли из занятия.";
}

/** Экран занятия: вход, комната LiveKit, после выхода — причина и возможность вернуться. */
export function VideoRoomScreen({ lessonId }: { lessonId: string }) {
  const info = useLoad(() => video.room(lessonId), [lessonId]);
  const [session, setSession] = useState<VideoJoin | null>(null);
  const [camera, setCamera] = useState(true);
  const [mic, setMic] = useState(true);
  const [left, setLeft] = useState<string>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function join() {
    setBusy(true);
    setError(undefined);
    setLeft(undefined);
    try {
      setSession(await video.join(lessonId));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const onDisconnected = useCallback(
    async (reason?: DisconnectReason) => {
      setSession(null);
      const fresh = await video.room(lessonId).catch(() => undefined);
      setLeft(endMessage(fresh, reason));
      info.reload();
    },
    [lessonId, info],
  );

  if (session) {
    return (
      // Своя обёртка строго по окну: у контейнера LiveKit в стилях position: relative и height: 100%,
      // они перебивают классы Tailwind, поэтому размер задаём снаружи.
      <div className="fixed inset-0 overflow-hidden">
        <LiveKitRoom
          serverUrl={session.url}
          token={session.token}
          connect
          video={camera}
          audio={mic}
          // Автоподстройка качества: слабое соединение — ниже разрешение, связь не рвётся (ТЗ, раздел 7).
          options={{
            adaptiveStream: true,
            dynacast: true,
            publishDefaults: { simulcast: true },
          }}
          onDisconnected={onDisconnected}
          onError={(e) => setError(errorText(e))}
          data-lk-theme="default"
        >
          <InRoom lessonId={lessonId} initial={session.room} />
        </LiveKitRoom>
      </div>
    );
  }

  if (info.error)
    return (
      <Centered>
        <Alert>{info.error}</Alert>
      </Centered>
    );
  if (!info.data)
    return (
      <Centered>
        <Spinner />
      </Centered>
    );
  const room = info.data;
  return (
    <Centered>
      <div className="w-full max-w-md space-y-5 rounded-2xl border border-line bg-surface p-6">
        <div>
          <p className="text-sm text-fg-soft">Занятие</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">
            {room.title}
          </h1>
          <p className="mt-1 text-sm text-fg-soft">
            {room.status === "active"
              ? "Идёт сейчас"
              : room.status === "ended"
                ? "Завершено"
                : "Ещё не началось"}{" "}
            · до {fmtTime(room.lesson_ends_at)}
          </p>
        </div>
        {left && <Alert kind="info">{left}</Alert>}
        {error && <Alert>{error}</Alert>}
        <div className="space-y-2 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={camera}
              onChange={(e) => setCamera(e.target.checked)}
              className="h-4 w-4 accent-brand"
            />
            Включить камеру
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={mic}
              onChange={(e) => setMic(e.target.checked)}
              className="h-4 w-4 accent-brand"
            />
            Включить микрофон
          </label>
        </div>
        <Button className="w-full" loading={busy} onClick={join}>
          {left ? "Вернуться в занятие" : "Войти в занятие"}
        </Button>
        {room.external_url && (
          <p className="text-sm text-fg-soft">
            Педагог указал и внешнюю ссылку:{" "}
            <a
              href={room.external_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand hover:underline"
            >
              открыть
            </a>
          </p>
        )}
        <p className="text-xs text-fg-soft">
          Бесплатное занятие длится до 40 минут с момента первого входа.
        </p>
        <Link
          href="/dashboard/schedule"
          className="block text-center text-sm text-fg-soft hover:text-fg"
        >
          ← К расписанию
        </Link>
      </div>
    </Centered>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh place-items-center bg-bg p-4">
      {children}
    </div>
  );
}

// ---------- внутри комнаты ----------

type Reaction = { id: number; emoji: string; name: string };

function InRoom({
  lessonId,
  initial,
}: {
  lessonId: string;
  initial: VideoRoom;
}) {
  const [room, setRoom] = useState(initial);
  const [panel, setPanel] = useState(false);
  const [reactions, setReactions] = useState<Reaction[]>([]);
  const counter = useRef(0);
  const { localParticipant } = useLocalParticipant();
  const [raised, setRaised] = useState(false);

  // Состояние комнаты с сервера: запись (запускается / идёт / сохраняется), лимит времени, права на экран.
  const busyRecording =
    room.recording === "starting" || room.recording === "stopping";
  useEffect(() => {
    const t = setInterval(
      () =>
        video
          .room(lessonId)
          .then(setRoom)
          .catch(() => {}),
      busyRecording ? 2000 : 8000,
    );
    return () => clearInterval(t);
  }, [lessonId, busyRecording]);

  const show = useCallback((emoji: string, name: string) => {
    const id = ++counter.current;
    setReactions((r) => [...r.slice(-8), { id, emoji, name }]);
    setTimeout(() => setReactions((r) => r.filter((x) => x.id !== id)), 3500);
  }, []);

  const { send } = useDataChannel("reaction", (msg) => {
    const emoji = new TextDecoder().decode(msg.payload);
    if (REACTIONS.includes(emoji)) show(emoji, msg.from?.name || "Участник");
  });

  function react(emoji: string) {
    send(new TextEncoder().encode(emoji), { reliable: false });
    show(emoji, "Вы");
  }

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      <div className="relative h-full min-w-0 flex-1 overflow-hidden">
        <RuConference />
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex flex-wrap items-start gap-2 p-3">
          <span className="pointer-events-auto rounded-lg bg-surface/90 px-3 py-1.5 text-sm font-medium text-fg shadow">
            {room.title}
          </span>
          {room.recording === "active" && (
            <span className="rounded-lg bg-danger px-2.5 py-1.5 text-sm font-medium text-white shadow">
              ● Идёт запись
            </span>
          )}
          <LimitTimer endsAt={room.limit_ends_at} />
          <span className="flex-1" />
          <span className="pointer-events-auto flex gap-1 rounded-lg bg-surface/90 p-1 shadow">
            <button
              onClick={() => {
                setRaised(!raised);
                void localParticipant.setAttributes({
                  hand: raised ? "" : "1",
                });
              }}
              className={`rounded-md px-2 py-1 text-sm ${raised ? "bg-tutor/20 text-tutor" : "text-fg hover:bg-muted"}`}
              aria-pressed={raised}
              title={raised ? "Опустить руку" : "Поднять руку"}
            >
              ✋ {raised ? "Опустить" : "Рука"}
            </button>
            {REACTIONS.map((e) => (
              <button
                key={e}
                onClick={() => react(e)}
                className="rounded-md px-1.5 py-1 hover:bg-muted"
                aria-label={`Реакция ${e}`}
              >
                {e}
              </button>
            ))}
            <button
              onClick={() => setPanel((p) => !p)}
              className="rounded-md px-2 py-1 text-sm text-fg hover:bg-muted"
              aria-expanded={panel}
            >
              {room.is_teacher ? "Управление" : "Участники"}
            </button>
          </span>
        </div>
        <div
          className="pointer-events-none absolute bottom-20 left-4 z-10 flex flex-col gap-1"
          aria-live="polite"
        >
          {reactions.map((r) => (
            <span
              key={r.id}
              className="w-fit animate-bounce rounded-full bg-surface/90 px-3 py-1 text-sm text-fg shadow"
            >
              <span className="text-xl">{r.emoji}</span> {r.name}
            </span>
          ))}
        </div>
      </div>
      {panel && (
        <SidePanel
          lessonId={lessonId}
          room={room}
          onRoom={setRoom}
          onClose={() => setPanel(false)}
        />
      )}
    </div>
  );
}

function LimitTimer({ endsAt }: { endsAt: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!endsAt) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [endsAt]);
  if (!endsAt) return null;
  const left = new Date(endsAt).getTime() - now;
  const min = Math.max(0, Math.floor(left / 60_000));
  const sec = String(Math.max(0, Math.floor((left % 60_000) / 1000))).padStart(
    2,
    "0",
  );
  const warn = left <= WARN_BEFORE_MS;
  return (
    <span
      className={`rounded-lg px-2.5 py-1.5 text-sm font-medium shadow ${warn ? "bg-tutor text-white" : "bg-surface/90 text-fg"}`}
      role={warn ? "alert" : "timer"}
      title="Бесплатное занятие длится до 40 минут"
    >
      {warn ? `Занятие закончится через ${min}:${sec}` : `Осталось ${min} мин`}
    </span>
  );
}

function SidePanel({
  lessonId,
  room,
  onRoom,
  onClose,
}: {
  lessonId: string;
  room: VideoRoom;
  onRoom: (r: VideoRoom) => void;
  onClose: () => void;
}) {
  const participants = useParticipants();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function act(action: () => Promise<VideoRoom>) {
    setBusy(true);
    setError(undefined);
    try {
      onRoom(await action());
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const people = participants.filter((p) => !p.identity.startsWith("EG_"));
  return (
    <aside className="flex h-full w-80 shrink-0 flex-col gap-4 overflow-y-auto border-l border-line bg-surface p-4 text-fg">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Участники · {people.length}</h2>
        <button
          onClick={onClose}
          className="text-fg-soft hover:text-fg"
          aria-label="Закрыть панель"
        >
          ✕
        </button>
      </div>
      {error && <Alert>{error}</Alert>}
      <ul className="space-y-1.5">
        {people.map((p) => {
          const teacher = safeRole(p.metadata) === "teacher";
          const allowed = room.screen_share.includes(p.identity);
          return (
            <li key={p.identity} className="flex items-center gap-2 text-sm">
              <span className="min-w-0 flex-1 truncate">
                {p.attributes?.hand === "1" && (
                  <span title="Поднята рука">✋ </span>
                )}
                {p.name || "Участник"}
                {teacher && <span className="text-fg-soft"> · педагог</span>}
                {p.isLocal && <span className="text-fg-soft"> (вы)</span>}
              </span>
              {room.is_teacher && !teacher && (
                <button
                  disabled={busy}
                  onClick={() =>
                    act(() => video.screenShare(lessonId, p.identity, !allowed))
                  }
                  className={`rounded-md border px-2 py-0.5 text-xs ${allowed ? "border-brand text-brand" : "border-line text-fg-soft hover:text-fg"}`}
                  title="Разрешить ученику показывать экран"
                >
                  {allowed ? "Экран: можно" : "Экран"}
                </button>
              )}
            </li>
          );
        })}
      </ul>

      {room.is_teacher && (
        <div className="space-y-2 border-t border-line pt-4">
          <h3 className="text-sm font-medium">Занятие</h3>
          <Button
            variant="secondary"
            className="w-full"
            loading={
              busy ||
              room.recording === "starting" ||
              room.recording === "stopping"
            }
            disabled={
              room.recording === "starting" || room.recording === "stopping"
            }
            onClick={() =>
              act(() =>
                video.recording(
                  lessonId,
                  room.recording === "active" ? "stop" : "start",
                ),
              )
            }
          >
            {
              {
                starting: "Запись запускается…",
                active: "Остановить запись",
                stopping: "Запись сохраняется…",
                none: "Включить запись",
              }[room.recording ?? "none"]
            }
          </Button>
          <p className="text-xs text-fg-soft">
            Занятие записывается само, как только кто-то входит; если остановить запись, сама она больше не включится.
            Запись увидят вы и ученики занятия; хранится 14 дней, не больше 3 записей.
          </p>
          <Button
            variant="ghost"
            className="w-full text-danger"
            onClick={() =>
              window.confirm("Завершить занятие для всех?") &&
              act(() => video.end(lessonId))
            }
          >
            Завершить для всех
          </Button>
        </div>
      )}
      <LiveTests lessonId={lessonId} teacher={room.is_teacher} />
    </aside>
  );
}

function safeRole(metadata: string | undefined): string | null {
  try {
    return metadata ? (JSON.parse(metadata).role ?? null) : null;
  } catch {
    return null;
  }
}

/** Тест на уроке прямо из комнаты: педагог видит прогресс, ученик — кнопку «Открыть тест». */
function LiveTests({
  lessonId,
  teacher,
}: {
  lessonId: string;
  teacher: boolean;
}) {
  const list = useLoad(
    () =>
      assessment.assignments(teacher ? "teacher" : "student", {
        lesson_id: lessonId,
      }),
    [lessonId, teacher],
  );
  const reload = list.reload;
  useEffect(() => {
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
  }, [reload]);
  const items = (list.data ?? []).filter((a) => a.kind === "live" || teacher);
  return (
    <div className="space-y-2 border-t border-line pt-4">
      <h3 className="text-sm font-medium">Тесты урока</h3>
      {!items.length ? (
        <p className="text-xs text-fg-soft">
          {teacher
            ? "Назначьте тест на этот урок в разделе «Назначение тестов» — здесь появится прогресс учеников."
            : "Пока нет."}
        </p>
      ) : (
        <ul className="space-y-2 text-sm">
          {items.map((a) => {
            const s = summary(a);
            return (
              <li key={a.id}>
                <Link
                  href={`/dashboard/assignments/${a.id}`}
                  target="_blank"
                  className="font-medium text-brand hover:underline"
                >
                  {a.title}
                </Link>
                <p className="text-xs text-fg-soft">
                  {teacher
                    ? `решают ${s.inProgress} · сдали ${s.submitted} из ${s.total}${a.closed ? " · завершён" : ""}`
                    : a.closed
                      ? "завершён"
                      : a.deadline
                        ? `до ${fmtDateTime(a.deadline)}`
                        : "открыть в новой вкладке"}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
