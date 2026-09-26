"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";

import { currentAccessToken } from "./api";
import { useAuth } from "./auth";

export type RealtimeEvent =
  | { type: "message"; conversation_id: string; message: import("./api").ChatMessage }
  | { type: "deleted"; conversation_id: string; message_id: string }
  | { type: "pinned"; conversation_id: string; message: null }
  | { type: "refresh"; conversation_id: string }
  | { type: "reconnected" };

type Listener = (e: RealtimeEvent) => void;

const RealtimeContext = createContext<{ subscribe: (l: Listener) => () => void } | null>(null);

/** Одно WebSocket-подключение на вкладку. Переподключается с нарастающей паузой;
 *  после восстановления шлёт «reconnected», чтобы экраны догрузили пропущенное. */
export function RealtimeProvider({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const listeners = useRef(new Set<Listener>());

  useEffect(() => {
    if (status !== "authenticated") return;
    let ws: WebSocket | null = null;
    let stopped = false;
    let attempt = 0;
    let wasConnected = false;
    let ping: ReturnType<typeof setInterval> | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const emit = (e: RealtimeEvent) => listeners.current.forEach((l) => l(e));

    async function connect() {
      const token = await currentAccessToken().catch(() => null);
      if (stopped || !token) return;
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/api/chat/ws`);
      ws.onopen = () => ws?.send(JSON.stringify({ type: "auth", token }));
      ws.onmessage = (msg) => {
        const data = JSON.parse(msg.data);
        if (data.type === "ready") {
          if (wasConnected) emit({ type: "reconnected" });
          wasConnected = true;
          attempt = 0;
          ping = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send('{"type":"ping"}'), 25000);
        } else if (data.type !== "pong") {
          emit(data);
        }
      };
      ws.onclose = () => {
        clearInterval(ping);
        if (stopped) return;
        attempt += 1;
        retry = setTimeout(connect, Math.min(30000, 1000 * 2 ** Math.min(attempt, 5)));
      };
    }

    connect();
    return () => {
      stopped = true;
      clearInterval(ping);
      clearTimeout(retry);
      ws?.close();
    };
  }, [status]);

  const [value] = useState(() => ({
    subscribe: (l: Listener) => {
      listeners.current.add(l);
      return () => {
        listeners.current.delete(l);
      };
    },
  }));

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtime(listener: Listener) {
  const ctx = useContext(RealtimeContext);
  const ref = useRef(listener);
  useEffect(() => {
    ref.current = listener;
  });
  useEffect(() => {
    if (!ctx) return;
    return ctx.subscribe((e) => ref.current(e));
  }, [ctx]);
}
