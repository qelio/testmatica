"use client";

import { LiveKitRoom, useDataChannel, useTracks, VideoTrack, type TrackReferenceOrPlaceholder } from "@livekit/components-react";
import { Track } from "livekit-client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { FinishButton } from "@/components/finish-attempt";
import { Alert, Badge, Button, Spinner } from "@/components/ui";
import { assessment, type Assignment, type ProctorJoin, video } from "@/lib/api";
import { lastAttempt } from "@/lib/assignments";
import { fmtDateTime, fmtTime } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";
import { decode, encode, EVENT_LABELS, PROCTOR_TOPIC, type ProctorState } from "@/lib/proctoring";
import { useRealtime } from "@/lib/realtime";

type Signal = { id: number; student: string; kind: string; at: string };

/** Наблюдение за тестом с прокторингом (ТЗ, раздел 7): сетка экранов, крупный вид, камера по запросу, сигналы о вкладках. */
export default function ProctoringPage() {
  const { id } = useParams<{ id: string }>();
  const [join, setJoin] = useState<ProctorJoin>();
  const [error, setError] = useState<string>();
  const assignment = useLoad(() => assessment.assignment(id), [id]);
  const reload = assignment.reload;

  useEffect(() => {
    video.proctorJoin(id).then(setJoin, (e) => setError(errorText(e)));
  }, [id]);
  // Статусы учеников (решает / сдал, число нарушений): сразу по событию и раз в 5 секунд — на случай обрыва WebSocket.
  useRealtime((e) => {
    if ((e.type === "assignment" && e.assignment_id === id) || e.type === "reconnected") reload();
  });
  useEffect(() => {
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
  }, [reload]);

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <Link href={`/dashboard/assignments/${id}`} className="text-sm text-fg-soft hover:text-fg">
        ← К тесту
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">Наблюдение{assignment.data ? `: ${assignment.data.title}` : ""}</h1>
      {(error || assignment.error) && <Alert>{error ?? assignment.error}</Alert>}
      {!join || !assignment.data ? (
        !error && <Spinner />
      ) : (
        <LiveKitRoom serverUrl={join.url} token={join.token} connect audio={false} video={false}>
          <Observer assignment={assignment.data} reload={reload} onError={setError} />
        </LiveKitRoom>
      )}
      <Recordings assignmentId={id} version={assignment.data} />
    </div>
  );
}

function Observer({ assignment, reload, onError }: { assignment: Assignment; reload: () => void; onError: (e: string) => void }) {
  const tracks = useTracks([Track.Source.ScreenShare, Track.Source.Camera], { onlySubscribed: true });
  const [states, setStates] = useState<Record<string, ProctorState>>({});
  const [signals, setSignals] = useState<Signal[]>([]);
  const [focus, setFocus] = useState<string | null>(null);
  const names = Object.fromEntries(assignment.students.map((s) => [s.student_id, s.full_name]));

  const onMessage = useCallback((msg: { payload: Uint8Array; from?: { identity: string } }) => {
    const data = decode(msg.payload);
    const from = msg.from?.identity;
    if (!data || !from) return;
    if (data.t === "state") setStates((s) => ({ ...s, [from]: data.state }));
    if (data.t === "event") {
      setSignals((list) => [{ id: Date.now() + Math.random(), student: from, kind: data.kind, at: data.at }, ...list].slice(0, 100));
      setStates((s) => {
        const cur = s[from] ?? { sharing: false, hidden: false, blurred: false, camera: false };
        const patch: Partial<ProctorState> =
          data.kind === "tab_hidden" ? { hidden: true } : data.kind === "tab_visible" ? { hidden: false }
          : data.kind === "focus_lost" ? { blurred: true } : data.kind === "focus_back" ? { blurred: false }
          : data.kind === "camera_on" ? { camera: true } : data.kind === "camera_off" ? { camera: false } : {};
        return { ...s, [from]: { ...cur, ...patch } };
      });
    }
  }, []);
  const { send } = useDataChannel(PROCTOR_TOPIC, onMessage);

  // Подключились — просим учеников прислать текущее состояние (вкладка, камера).
  useEffect(() => {
    const t = setTimeout(() => void send(encode({ t: "hello" }), { reliable: true }).catch(() => {}), 800);
    return () => clearTimeout(t);
  }, [send]);

  const camera = (student: string, on: boolean) =>
    void send(encode({ t: "camera", on }), { reliable: true, destinationIdentities: [student] }).catch(() => {});

  const screenOf = (sid: string) => tracks.find((t) => t.participant.identity === sid && t.source === Track.Source.ScreenShare);
  const cameraOf = (sid: string) => tracks.find((t) => t.participant.identity === sid && t.source === Track.Source.Camera);
  const rows = assignment.students.map((row) => ({ row, last: lastAttempt(row) }));
  const shows = (sid: string) => {
    const screen = screenOf(sid);
    return !!screen && "publication" in screen && !!screen.publication;
  };
  const focused = focus ? rows.find((r) => r.row.student_id === focus) : null;
  // Порядок: показывают экран → решают, но экран выключен → не решают (не начали или сдали).
  const rest = rows.filter((r) => r.row.student_id !== focus);
  const solving = rest.filter((r) => r.last?.status === "in_progress");
  const groups = [
    { key: "shows", title: "Показывают экран", items: solving.filter((r) => shows(r.row.student_id)) },
    { key: "off", title: "Решают, экран выключен", items: solving.filter((r) => !shows(r.row.student_id)) },
    { key: "idle", title: "Не решают", items: rest.filter((r) => r.last?.status !== "in_progress") },
  ];

  const tile = ({ row, last }: (typeof rows)[number], big = false) => (
    <Tile
      key={row.student_id}
      big={big}
      name={row.full_name}
      screen={screenOf(row.student_id)}
      cam={cameraOf(row.student_id)}
      state={states[row.student_id]}
      status={last?.status}
      alerts={row.proctor_alerts}
      onCamera={(on) => camera(row.student_id, on)}
      onClick={() => setFocus(big ? null : row.student_id)}
      finish={
        last?.status === "in_progress" ? (
          <FinishButton attemptId={last.id} name={row.full_name} onDone={reload} onError={onError} className="h-8 rounded-lg px-2 text-xs font-medium text-danger hover:bg-danger/10" />
        ) : null
      }
    />
  );

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="space-y-5">
        {focused && tile(focused, true)}
        {rows.every((r) => r.last?.status !== "in_progress") && (
          <p className="text-sm text-fg-soft">Сейчас никто не решает тест. Экраны появятся, когда ученики начнут.</p>
        )}
        {groups.map(
          (g) =>
            g.items.length > 0 && (
              <section key={g.key} className="space-y-2">
                <h2 className={`text-sm font-semibold ${g.key === "off" ? "text-danger" : "text-fg-soft"}`}>
                  {g.title} · {g.items.length}
                </h2>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{g.items.map((r) => tile(r))}</div>
              </section>
            ),
        )}
      </div>
      <aside className="space-y-2 rounded-2xl border border-line bg-surface p-4 lg:sticky lg:top-22 lg:max-h-[calc(100dvh-7.5rem)] lg:overflow-y-auto">
        <h2 className="font-semibold">Сигналы</h2>
        {signals.length === 0 && <p className="text-sm text-fg-soft">Пока всё спокойно. Здесь появится, если ученик уйдёт со вкладки или перестанет показывать экран.</p>}
        <ul className="space-y-1.5 text-sm">
          {signals.map((s) => (
            <li key={s.id} className={EVENT_LABELS[s.kind]?.alert ? "text-danger" : "text-fg-soft"}>
              <span className="tabular-nums">{fmtTime(s.at)}</span> <b>{names[s.student] ?? "Ученик"}</b> {EVENT_LABELS[s.kind]?.text ?? s.kind}
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}

function Tile({
  name,
  screen,
  cam,
  state,
  status,
  alerts,
  big,
  onCamera,
  onClick,
  finish,
}: {
  name: string;
  screen?: TrackReferenceOrPlaceholder;
  cam?: TrackReferenceOrPlaceholder;
  state?: ProctorState;
  status?: string;
  alerts: number;
  big?: boolean;
  onCamera: (on: boolean) => void;
  onClick: () => void;
  finish?: React.ReactNode;
}) {
  const away = state?.hidden || state?.blurred;
  const noScreen = status === "in_progress" && !(screen && "publication" in screen && screen.publication);
  const placeholder = status === "submitted" ? "Работа сдана" : status === "in_progress" ? "Экран не показывается" : "Ещё не начал";
  return (
    <div
      className={`overflow-hidden rounded-2xl border bg-surface ${away || noScreen ? "border-danger ring-2 ring-danger/40" : "border-line"} ${status !== "in_progress" && !big ? "opacity-70" : ""}`}
    >
      <button type="button" onClick={onClick} className="relative block w-full bg-black" title={big ? "Вернуться к сетке" : "Смотреть крупно"}>
        <div className={big ? "aspect-video max-h-[70dvh]" : "aspect-video"}>
          {screen && "publication" in screen && screen.publication ? (
            <VideoTrack trackRef={screen} className="h-full w-full object-contain" />
          ) : (
            <span className="grid h-full place-items-center text-sm text-white/60">{placeholder}</span>
          )}
        </div>
        {cam && "publication" in cam && cam.publication && (
          <div className="absolute right-2 bottom-2 w-1/4 overflow-hidden rounded-lg border border-white/30">
            <VideoTrack trackRef={cam} className="aspect-video w-full object-cover" />
          </div>
        )}
      </button>
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
        <span className="min-w-0 flex-1 truncate font-medium">{name}</span>
        {state?.hidden && <Badge tone="warn">ушёл со вкладки</Badge>}
        {!state?.hidden && state?.blurred && <Badge tone="warn">другое окно</Badge>}
        {alerts > 0 && <span className="text-xs text-danger">нарушений: {alerts}</span>}
        {status === "in_progress" && (
          <Button variant="ghost" className="h-8 px-2 text-xs" onClick={() => onCamera(!state?.camera)}>
            {state?.camera ? "Выключить камеру" : "Камера"}
          </Button>
        )}
        {finish}
      </div>
    </div>
  );
}

function fmtDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} с`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s ? `${m} мин ${s} с` : `${m} мин`;
}

/** Записи экранов. Обновляются вместе со статусами учеников (событие или раз в 5 секунд): запись появляется,
 *  когда ученик начал показ, и становится доступной через несколько секунд после того, как он закончил. */
function Recordings({ assignmentId, version }: { assignmentId: string; version: unknown }) {
  const list = useLoad(() => video.proctorRecordings(assignmentId), [assignmentId]);
  const { reload } = list;
  useEffect(() => {
    if (version) void reload();
  }, [version, reload]);
  // Пока запись дописывается (ученик сдал работу) — проверяем чаще, не дожидаясь событий.
  const pending = !!list.data?.some((r) => r.status === "recording");
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(reload, 3000);
    return () => clearInterval(t);
  }, [pending, reload]);
  if (!list.data?.length) return null;
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold">Записи экранов</h2>
      <p className="text-sm text-fg-soft">Хранятся 2 недели. Если ученик перезапускал показ экрана, записей несколько.</p>
      <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
        {list.data.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm">
            <span className="min-w-0 flex-1">
              <b>{r.student_name}</b> · {fmtDateTime(r.started_at)}
              {r.duration_s && r.duration_s > 0 ? ` · ${fmtDuration(r.duration_s)}` : ""}
            </span>
            {r.status === "recording" && <Badge tone="brand">идёт запись</Badge>}
            {r.status === "failed" && <Badge tone="warn">не записалось</Badge>}
            {r.url && (
              <a href={r.url} target="_blank" rel="noreferrer" className="text-brand-text hover:underline">
                Смотреть
              </a>
            )}
            {r.download_url && (
              <a href={r.download_url} className="text-fg-soft hover:text-fg">
                Скачать
              </a>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
