"use client";

import { useLocalParticipant, useParticipants, useTracks } from "@livekit/components-react";
import { LocalTrack, RemoteTrack, Track } from "livekit-client";
import { useEffect } from "react";

// Режим повышенного качества показа экрана (решение №63): педагог включает его, когда у учеников «мылит» картинку.
// Состояние — атрибут участника LiveKit: доходит до всех сразу, в том числе до подключившихся позже.
const ATTRIBUTE = "screen_hq";
const NORMAL_BITRATE = 2_500_000;
const HIGH_BITRATE = 4_000_000;
const HIGH_PLAYOUT_DELAY_S = 0.5;

function useHighQuality(): boolean {
  return useParticipants().some((p) => p.attributes?.[ATTRIBUTE] === "1");
}

/** Меняет битрейт верхнего слоя уже идущего показа: заново выбирать экран не нужно. */
async function setTopBitrate(track: LocalTrack, bitrate: number) {
  const sender = track.sender;
  const params = sender?.getParameters();
  if (!sender || !params?.encodings.length) return;
  const top = params.encodings.reduce((a, b) => ((b.scaleResolutionDownBy ?? 1) < (a.scaleResolutionDownBy ?? 1) ? b : a));
  if (top.maxBitrate === bitrate) return;
  top.maxBitrate = bitrate;
  await sender.setParameters(params);
}

/** Применяет режим к показам экрана в комнате: у показывающего — битрейт, у зрителей — задержка воспроизведения
 *  (успевают дойти повторы потерянных пакетов). Камера и голос идут без задержки. */
export function useScreenQuality() {
  const high = useHighQuality();
  const screens = useTracks([Track.Source.ScreenShare]);
  const key = screens.map((t) => `${t.publication.trackSid}_${t.publication.isSubscribed}`).join();

  useEffect(() => {
    for (const { publication } of screens) {
      const track = publication.track;
      if (track instanceof RemoteTrack) track.setPlayoutDelay(high ? HIGH_PLAYOUT_DELAY_S : 0);
      else if (track instanceof LocalTrack) void setTopBitrate(track, high ? HIGH_BITRATE : NORMAL_BITRATE).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- состав показов — в key
  }, [key, high]);
}

/** Переключатель для педагога: в управлении конференцией и на странице показа на доске. */
export function ScreenQualityToggle() {
  const { localParticipant } = useLocalParticipant();
  const high = useHighQuality();
  return (
    <label className="flex cursor-pointer items-start gap-2 text-sm">
      <input
        type="checkbox"
        className="mt-0.5 accent-brand"
        checked={high}
        onChange={(e) => void localParticipant.setAttributes({ [ATTRIBUTE]: e.target.checked ? "1" : "" })}
      />
      <span>
        Повышенное качество экрана
        <span className="block text-xs text-fg-soft">Картинка чётче, но экран отстаёт от голоса на полсекунды. Нужен интернет от 5 Мбит/с.</span>
      </span>
    </label>
  );
}
