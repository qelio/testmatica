"use client";

import { LiveKitRoom, RoomAudioRenderer, StartAudio, useTracks, VideoTrack } from "@livekit/components-react";
import { Track } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { useScreenQuality } from "@/components/screen-quality";
import { board, type BoardCreated, type BoardStatus } from "@/lib/api";

/** Интерактивная доска в кабинете (решение №53): без входа в аккаунт показывает код; педагог вводит его у себя
 *  в «Показать на доске» — и его экран появляется здесь. Можно развернуть во весь экран. */
export default function BoardPage() {
  const [session, setSession] = useState<BoardCreated | null>(null);
  const [status, setStatus] = useState<BoardStatus | null>(null);
  const [error, setError] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const creating = useRef(false);

  const fresh = useCallback(async () => {
    if (creating.current) return;
    creating.current = true;
    try {
      const s = await board.create();
      setSession(s);
      setStatus(null);
      setError(false);
    } catch {
      setError(true);
    } finally {
      creating.current = false;
    }
  }, []);

  // Первый код — сразу при открытии страницы.
  useEffect(() => {
    let alive = true;
    board.create().then(
      (s) => alive && setSession(s),
      () => alive && setError(true),
    );
    return () => {
      alive = false;
    };
  }, []);

  // Не удалось получить код (нет сети) — пробуем снова.
  useEffect(() => {
    if (session) return;
    const t = setInterval(() => void fresh(), 5000);
    return () => clearInterval(t);
  }, [session, fresh]);

  // Ждём педагога: спрашиваем статус; код истёк или показ закончился — берём новый код.
  useEffect(() => {
    if (!session) return;
    let alive = true;
    const tick = async () => {
      try {
        const st = await board.status(session.id, session.secret);
        if (!alive) return;
        if (st.status === "expired" || st.status === "ended") return void fresh();
        setStatus((prev) => (prev?.status === st.status && prev.token ? prev : st));
        setError(false);
      } catch {
        if (alive) setError(true);
      }
    };
    void tick();
    const t = setInterval(tick, 2000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [session, fresh]);

  useEffect(() => {
    const on = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", on);
    return () => document.removeEventListener("fullscreenchange", on);
  }, []);

  function toggleFullscreen() {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void document.documentElement.requestFullscreen?.().catch(() => {});
  }

  const live = status?.status === "live" && status.url && status.token;

  return (
    <div className="fixed inset-0 flex flex-col bg-black text-white" onDoubleClick={toggleFullscreen}>
      {live ? (
        <LiveKitRoom serverUrl={status.url!} token={status.token!} connect audio={false} video={false} className="flex-1">
          <Screen teacher={status.teacher_name} />
          <RoomAudioRenderer />
          <StartAudio label="Включить звук" className="absolute bottom-4 left-4 rounded-xl bg-white/15 px-4 py-2 text-sm hover:bg-white/25" />
        </LiveKitRoom>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-8 px-6 text-center">
          <p className="text-2xl text-white/70 sm:text-3xl">Код для показа экрана на доске</p>
          <p className="font-mono text-7xl font-bold tracking-[0.3em] tabular-nums sm:text-9xl" aria-live="polite">
            {session ? `${session.code.slice(0, 3)} ${session.code.slice(3)}` : "··· ···"}
          </p>
          <p className="max-w-2xl text-xl text-white/70 sm:text-2xl">
            Откройте <b className="text-white">testmatica.ru</b> на своём компьютере → «Показать на доске» и введите этот код.
          </p>
          {error && <p className="text-lg text-red-300">Нет связи с сервером — пробую снова…</p>}
        </div>
      )}
      {!fullscreen && (
        <div className="absolute top-4 right-4 flex gap-2">
          {live && session && (
            <button
              type="button"
              onClick={async () => {
                await board.end(session.id, session.secret).catch(() => {});
                void fresh();
              }}
              className="rounded-xl bg-white/15 px-4 py-2 text-sm hover:bg-white/25"
            >
              Новый код
            </button>
          )}
          <button type="button" onClick={toggleFullscreen} className="rounded-xl bg-white/15 px-4 py-2 text-sm font-medium hover:bg-white/25">
            ⛶ Во весь экран
          </button>
        </div>
      )}
    </div>
  );
}

/** Экран педагога — на всю доску, с сохранением пропорций. */
function Screen({ teacher }: { teacher: string | null }) {
  const tracks = useTracks([Track.Source.ScreenShare], { onlySubscribed: true });
  const screen = tracks[0];
  useScreenQuality();
  if (!screen) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <p className="text-3xl">{teacher ? `${teacher} подключается…` : "Педагог подключается…"}</p>
        <p className="text-xl text-white/60">Изображение появится, когда педагог выберет, что показать.</p>
      </div>
    );
  }
  return <VideoTrack trackRef={screen} className="h-full w-full object-contain" />;
}
