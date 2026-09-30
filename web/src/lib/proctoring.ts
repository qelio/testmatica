// Сообщения прокторинга через канал данных LiveKit (тема "proctor").
// Ученик → педагогу: сигналы (вкладка, фокус, показ экрана) и текущее состояние. Педагог → ученику: камера, «кто здесь».

import type { ProctorEventKind } from "@/lib/api";

export const PROCTOR_TOPIC = "proctor";

export type ProctorState = { sharing: boolean; hidden: boolean; blurred: boolean; camera: boolean };
export type ProctorMessage =
  | { t: "event"; kind: ProctorEventKind; at: string }
  | { t: "state"; state: ProctorState }
  | { t: "camera"; on: boolean }
  | { t: "hello" };

const encoder = new TextEncoder();
const decoder = new TextDecoder();

export function encode(msg: ProctorMessage): Uint8Array<ArrayBuffer> {
  return encoder.encode(JSON.stringify(msg));
}

export function decode(payload: Uint8Array): ProctorMessage | null {
  try {
    return JSON.parse(decoder.decode(payload)) as ProctorMessage;
  } catch {
    return null;
  }
}

export const EVENT_LABELS: Record<string, { text: string; alert: boolean }> = {
  consent: { text: "дал согласие на мониторинг", alert: false },
  screen_share_started: { text: "показывает экран", alert: false },
  screen_share_stopped: { text: "прекратил показ экрана", alert: true },
  tab_hidden: { text: "ушёл со вкладки теста", alert: true },
  tab_visible: { text: "вернулся на вкладку", alert: false },
  focus_lost: { text: "переключился на другое окно", alert: true },
  focus_back: { text: "вернулся в окно теста", alert: false },
  camera_requested: { text: "педагог запросил камеру", alert: false },
  camera_on: { text: "включил камеру", alert: false },
  camera_off: { text: "камера выключена", alert: false },
  finished_by_teacher: { text: "педагог завершил работу", alert: false },
};
