"use client";

/** Доска вживую (решение №60): WebSocket к сервису whiteboard. Свои правки применяются сразу и уходят на сервер;
 *  пока нет связи — копятся и отправляются после переподключения, затем доска перечитывается целиком. */

import { useCallback, useEffect, useRef, useState } from "react";

import { type BoardItem, type BoardRole, type BoardSummary, currentAccessToken } from "@/lib/api";

export type Ops = { upsert?: BoardItem[]; delete?: string[] };
export type Remote =
  | { type: "ops"; upsert: BoardItem[]; delete: string[] }
  | { type: "draft"; from: string; item: BoardItem }
  | { type: "board"; board: BoardSummary; role: BoardRole }
  | { type: "reconnected" }
  | { type: "closed"; code: number }
  | { type: "error"; message: string };

export type SyncStatus = "connecting" | "online" | "offline";

export function useBoardSync(boardId: string, onRemote: (e: Remote) => void) {
  const [status, setStatus] = useState<SyncStatus>("connecting");
  const ws = useRef<WebSocket | null>(null);
  const conn = useRef<string | null>(null);
  const queue = useRef<Ops[]>([]);
  const handler = useRef(onRemote);
  useEffect(() => {
    handler.current = onRemote;
  });

  useEffect(() => {
    let stopped = false;
    let attempt = 0;
    let wasOnline = false;
    let ping: ReturnType<typeof setInterval> | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;

    async function connect() {
      const token = await currentAccessToken().catch(() => null);
      if (stopped || !token) return;
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${proto}://${window.location.host}/api/whiteboard/ws`);
      ws.current = socket;
      socket.onopen = () => socket.send(JSON.stringify({ type: "auth", token, board_id: boardId }));
      socket.onmessage = (msg) => {
        const data = JSON.parse(msg.data);
        if (data.type === "ready") {
          conn.current = data.conn;
          attempt = 0;
          setStatus("online");
          ping = setInterval(() => socket.readyState === WebSocket.OPEN && socket.send('{"type":"ping"}'), 25000);
          for (const ops of queue.current.splice(0)) socket.send(JSON.stringify({ type: "ops", ...ops }));
          if (wasOnline) handler.current({ type: "reconnected" });
          wasOnline = true;
        } else if (data.from && data.from === conn.current) {
          // своё эхо
        } else if (data.type === "ops" || data.type === "draft" || data.type === "board") {
          handler.current(data);
        } else if (data.type === "error") {
          handler.current({ type: "error", message: data.message });
        }
      };
      socket.onclose = (e) => {
        clearInterval(ping);
        if (stopped) return;
        setStatus("offline");
        // Доступ закрыли, доску удалили или вход недействителен — не переподключаемся.
        if ([4403, 4404].includes(e.code)) {
          handler.current({ type: "closed", code: e.code });
          return;
        }
        attempt += 1;
        retry = setTimeout(connect, Math.min(15000, 500 * 2 ** Math.min(attempt, 5)));
      };
    }

    connect();
    return () => {
      stopped = true;
      clearInterval(ping);
      clearTimeout(retry);
      ws.current?.close();
    };
  }, [boardId]);

  const send = useCallback((ops: Ops) => {
    if (!ops.upsert?.length && !ops.delete?.length) return;
    const socket = ws.current;
    if (socket && socket.readyState === WebSocket.OPEN && conn.current) socket.send(JSON.stringify({ type: "ops", ...ops }));
    else queue.current.push(ops);
  }, []);

  const sendDraft = useCallback((item: BoardItem) => {
    const socket = ws.current;
    if (socket && socket.readyState === WebSocket.OPEN && conn.current) socket.send(JSON.stringify({ type: "draft", item }));
  }, []);

  return { status, send, sendDraft };
}
