"use client";

import { ConnectionState, type LocalTrackPublication, Room, RoomEvent, Track } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { Alert, Button, Spinner } from "@/components/ui";
import { assessment, type ProctorEventKind, video } from "@/lib/api";
import { fmtTime } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";
import { decode, encode, EVENT_LABELS, PROCTOR_TOPIC, type ProctorState } from "@/lib/proctoring";

/**
 * Прокторинг на стороне ученика: пока идёт тест, экран показывается педагогу (весь экран),
 * уход со вкладки и из окна сразу сообщается педагогу и пишется в журнал, камера включается по запросу педагога.
 * Без показа экрана тест закрыт шторкой — ответы и таймер при этом сохраняются.
 */
export function ProctorGuard({ attemptId, assignmentId, children }: { attemptId: string; assignmentId: string; children: React.ReactNode }) {
  const roomRef = useRef<Room | null>(null);
  const [connected, setConnected] = useState(false);
  const [state, setState] = useState<ProctorState>({ sharing: false, hidden: false, blurred: false, camera: false });
  const stateRef = useRef(state);
  const [error, setError] = useState<string>();
  const [warning, setWarning] = useState<string>();
  const [busy, setBusy] = useState(false);

  const update = useCallback((patch: Partial<ProctorState>) => {
    stateRef.current = { ...stateRef.current, ...patch };
    setState(stateRef.current);
    const room = roomRef.current;
    if (room?.state === ConnectionState.Connected) {
      void room.localParticipant.publishData(encode({ t: "state", state: stateRef.current }), { reliable: true, topic: PROCTOR_TOPIC });
    }
  }, []);

  // Событие: педагогу — сразу через комнату, в журнал — через API.
  const report = useCallback(
    (kind: ProctorEventKind) => {
      const room = roomRef.current;
      if (room?.state === ConnectionState.Connected) {
        void room.localParticipant.publishData(encode({ t: "event", kind, at: new Date().toISOString() }), {
          reliable: true,
          topic: PROCTOR_TOPIC,
        });
      }
      assessment.proctorEvent(attemptId, kind).catch(() => {});
    },
    [attemptId],
  );

  useEffect(() => {
    const room = new Room({ adaptiveStream: false, dynacast: false });
    roomRef.current = room;
    let cancelled = false;

    room.on(RoomEvent.LocalTrackUnpublished, (pub: LocalTrackPublication) => {
      if (pub.source === Track.Source.ScreenShare) {
        update({ sharing: false });
        report("screen_share_stopped");
      } else if (pub.source === Track.Source.Camera) {
        update({ camera: false });
      }
    });
    room.on(RoomEvent.DataReceived, (payload, _p, _kind, topic) => {
      if (topic !== PROCTOR_TOPIC) return;
      const msg = decode(payload);
      if (msg?.t === "hello") update({});
      if (msg?.t === "camera") {
        report(msg.on ? "camera_requested" : "camera_off");
        room.localParticipant
          .setCameraEnabled(msg.on)
          .then(() => {
            update({ camera: msg.on });
            if (msg.on) report("camera_on");
          })
          .catch(() => setWarning("Педагог попросил включить камеру, но браузер не дал к ней доступ. Разрешите камеру для этого сайта."));
      }
    });
    room.on(RoomEvent.Disconnected, () => setConnected(false));
    room.on(RoomEvent.Reconnected, () => update({}));

    (async () => {
      try {
        const join = await video.proctorJoin(assignmentId);
        if (cancelled) return;
        await room.connect(join.url, join.token, { autoSubscribe: false });
        if (!cancelled) setConnected(true);
      } catch (e) {
        if (!cancelled) setError(errorText(e) || "Не удалось подключиться к прокторингу");
      }
    })();
    return () => {
      cancelled = true;
      void room.disconnect();
      roomRef.current = null;
    };
  }, [assignmentId, report, update]);

  // Уход со вкладки и из окна браузера.
  useEffect(() => {
    const onVisibility = () => {
      const hidden = document.visibilityState === "hidden";
      update({ hidden });
      report(hidden ? "tab_hidden" : "tab_visible");
    };
    const onBlur = () => {
      if (document.visibilityState === "hidden") return; // уже сообщили как смену вкладки
      update({ blurred: true });
      report("focus_lost");
    };
    const onFocus = () => {
      if (!stateRef.current.blurred) return;
      update({ blurred: false });
      report("focus_back");
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
    };
  }, [report, update]);

  async function share() {
    const room = roomRef.current;
    if (!room) return;
    setBusy(true);
    setWarning(undefined);
    try {
      const pub = await room.localParticipant.setScreenShareEnabled(true, {
        audio: false,
        video: { displaySurface: "monitor" },
        selfBrowserSurface: "exclude",
        surfaceSwitching: "exclude",
      });
      // Нужен весь экран: окно или вкладка не покажут, что ещё открыто.
      const surface = pub?.track?.mediaStreamTrack.getSettings().displaySurface;
      if (surface && surface !== "monitor") {
        await room.localParticipant.setScreenShareEnabled(false);
        setWarning("Выберите «Весь экран» — показ отдельного окна или вкладки не подходит.");
        return;
      }
      update({ sharing: true });
      report("screen_share_started");
    } catch {
      setWarning("Показ экрана не начался. Нажмите кнопку ещё раз и выберите «Весь экран».");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative">
      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-brand/30 bg-brand/5 px-4 py-2 text-sm">
        <span className={`h-2 w-2 rounded-full ${state.sharing ? "bg-danger" : "bg-line"}`} aria-hidden />
        <span className="flex-1">
          Тест с прокторингом: {state.sharing ? "ваш экран виден педагогу" : "экран не показывается"}
          {state.camera && " · камера включена по запросу педагога"}
        </span>
      </div>
      {warning && <div className="mb-4"><Alert>{warning}</Alert></div>}
      {children}
      {!state.sharing && (
        <div className="fixed inset-0 z-30 grid place-items-center bg-bg/85 p-4 backdrop-blur-sm">
          <div className="max-w-md space-y-4 rounded-2xl border border-line bg-surface p-6 text-center shadow-lg">
            <h2 className="text-lg font-semibold">Покажите экран, чтобы продолжить</h2>
            <p className="text-sm text-fg-soft">
              Это тест с прокторингом: педагог видит ваш экран, пока вы решаете. Выберите «Весь экран». Таймер теста идёт.
            </p>
            {error ? (
              <Alert>{error}</Alert>
            ) : !connected ? (
              <Spinner />
            ) : (
              <Button onClick={share} loading={busy} className="w-full">
                Показать экран
              </Button>
            )}
            {warning && <p className="text-sm text-danger">{warning}</p>}
          </div>
        </div>
      )}
    </div>
  );
}


/** Журнал прокторинга попытки — педагогу при разборе работы. */
export function ProctorLog({ attemptId }: { attemptId: string }) {
  const events = useLoad(() => assessment.proctorEvents(attemptId), [attemptId]);
  if (!events.data) return null;
  const alerts = events.data.filter((e) => EVENT_LABELS[e.kind]?.alert).length;
  return (
    <details className="rounded-2xl border border-line bg-surface p-4 text-sm" open={alerts > 0}>
      <summary className="cursor-pointer font-medium">
        Прокторинг: {alerts ? `нарушений — ${alerts}` : "нарушений нет"}
      </summary>
      <ul className="mt-2 space-y-1">
        {events.data.map((e, i) => (
          <li key={i} className={EVENT_LABELS[e.kind]?.alert ? "text-danger" : "text-fg-soft"}>
            <span className="tabular-nums">{fmtTime(e.at)}</span> — {EVENT_LABELS[e.kind]?.text ?? e.kind}
          </li>
        ))}
      </ul>
    </details>
  );
}
