"use client";

import { LiveKitRoom, useLocalParticipant, useTracks, VideoTrack } from "@livekit/components-react";
import { Track } from "livekit-client";
import { useState } from "react";

import { ScreenQualityToggle, useScreenQuality } from "@/components/screen-quality";
import { Alert, Button } from "@/components/ui";
import { board } from "@/lib/api";
import { errorText } from "@/lib/hooks";

type Pairing = { id: string; url: string; token: string };

/** Показать свой экран на интерактивной доске (решение №53): на доске открыт testmatica.ru/board с кодом —
 *  педагог вводит код здесь и выбирает, что показать (экран, окно или вкладку со звуком). */
export default function BoardCastPage() {
  const [code, setCode] = useState("");
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function connect(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      setPairing(await board.pair(code));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    if (pairing) await board.stop(pairing.id).catch(() => {});
    setPairing(null);
    setCode("");
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Показать на доске</h1>
      {error && <Alert>{error}</Alert>}
      {!pairing ? (
        <div className="space-y-4 rounded-2xl border border-line bg-surface p-5">
          <ol className="list-inside list-decimal space-y-1 text-sm text-fg-soft">
            <li>
              На доске откройте в браузере <b className="text-fg">testmatica.ru/board</b> — входить в аккаунт не нужно, там появится код.
            </li>
            <li>Введите код ниже и выберите, что показать: весь экран, окно или вкладку.</li>
            <li>На доске нажмите «Во весь экран» (или дважды коснитесь экрана).</li>
          </ol>
          <form onSubmit={connect} className="flex flex-wrap items-center gap-3">
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              inputMode="numeric"
              autoComplete="off"
              placeholder="000000"
              aria-label="Код с доски"
              className="h-12 w-44 rounded-xl border border-line bg-surface px-4 text-center font-mono text-2xl tracking-[0.3em] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
            />
            <Button type="submit" loading={busy} disabled={code.length !== 6} className="h-12">
              Подключиться
            </Button>
          </form>
        </div>
      ) : (
        <LiveKitRoom serverUrl={pairing.url} token={pairing.token} connect audio={false} video={false} onDisconnected={() => setPairing(null)}>
          <Presenter onStop={stop} />
        </LiveKitRoom>
      )}
    </div>
  );
}

function Presenter({ onStop }: { onStop: () => void }) {
  const { localParticipant, isScreenShareEnabled } = useLocalParticipant();
  const mine = useTracks([Track.Source.ScreenShare]).filter((t) => t.participant.isLocal);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  useScreenQuality();

  async function share() {
    setBusy(true);
    setError(undefined);
    try {
      // Звук — если показывают вкладку с видео; окно и экран передаются без звука.
      await localParticipant.setScreenShareEnabled(true, { audio: true, selfBrowserSurface: "exclude", contentHint: "text" });
    } catch {
      setError("Показ не начался. Нажмите кнопку ещё раз и выберите экран, окно или вкладку.");
    } finally {
      setBusy(false);
    }
  }

  async function change() {
    await localParticipant.setScreenShareEnabled(false);
    await share();
  }

  return (
    <div className="space-y-4 rounded-2xl border border-line bg-surface p-5">
      {error && <Alert>{error}</Alert>}
      <p className="text-sm">
        {isScreenShareEnabled ? (
          <span className="font-medium text-ok">● Идёт показ на доске</span>
        ) : (
          <span>Доска подключена. Выберите, что показать.</span>
        )}
      </p>
      {mine[0] && (
        <div className="overflow-hidden rounded-xl border border-line bg-black">
          <VideoTrack trackRef={mine[0]} className="max-h-72 w-full object-contain" />
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {isScreenShareEnabled ? (
          <Button variant="secondary" onClick={change} loading={busy}>
            Показать другое
          </Button>
        ) : (
          <Button onClick={share} loading={busy}>
            Показать экран
          </Button>
        )}
        <Button variant="ghost" className="text-danger" onClick={onStop}>
          Остановить показ
        </Button>
      </div>
      <ScreenQualityToggle />
      <p className="text-xs text-fg-soft">Не закрывайте эту вкладку, пока идёт показ: закроете — доска снова покажет код.</p>
    </div>
  );
}
