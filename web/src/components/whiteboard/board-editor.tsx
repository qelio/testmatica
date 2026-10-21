"use client";

/** Доска (решение №60): бесконечный лист, перо, фломастер, маркер, ластик, фигуры, текст, формулы, картинки,
 *  произвольное выделение и перенос; бумага — линейка, клетка, точки, цвет. Правки видны всем вживую. */

import {
  Brush,
  Circle,
  Diamond,
  Eraser,
  Expand,
  Hand,
  Highlighter,
  ImagePlus,
  LassoSelect,
  Maximize,
  Maximize2,
  Minimize,
  Minus,
  MoveHorizontal,
  MoveRight,
  Move3d,
  Pen,
  Redo2,
  Shrink,
  Sigma,
  Square,
  Trash2,
  Triangle,
  Type,
  Undo2,
  WifiOff,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { Alert, Button, Modal } from "@/components/ui";
import {
  type Board,
  type BoardAccess,
  type BoardItem,
  type BoardRole,
  type BoardSummary,
  type PaperColor,
  type PaperStyle,
  uploadFile,
  whiteboard,
} from "@/lib/api";
import { errorText } from "@/lib/hooks";

import { formulaHtml, ItemView } from "./items";
import {
  bbox,
  type Box,
  hits,
  inPolygon,
  INKS,
  newId,
  PAPER_COLORS,
  PAPER_STEP,
  PAPER_STYLES,
  type PenTool,
  type Pt,
  PX_PER_MM,
  type ShapeKind,
  SHAPES,
  SIZES_MM,
  TOOL_SCALE,
  transform,
  union,
} from "./model";
import { type Ops, type Remote, useBoardSync } from "./use-board-sync";

type Tool = PenTool | "eraser" | "select" | "pan" | "text" | "shape";
type Tab = "draw" | "insert" | "view";
type View = { x: number; y: number; zoom: number };
type Gesture =
  | { kind: "draw"; item: BoardItem; sentAt: number }
  | { kind: "shape"; item: BoardItem }
  | { kind: "erase"; ids: Set<string> }
  | { kind: "lasso"; pts: Pt[] }
  | { kind: "move"; sx: number; sy: number; orig: BoardItem[] }
  | { kind: "scale"; box: Box; orig: BoardItem[] }
  | { kind: "pan"; cx: number; cy: number; view: View };

const SHAPE_ICONS: Record<ShapeKind, React.ReactNode> = {
  line: <Minus size={18} />,
  arrow: <MoveRight size={18} />,
  arrow2: <MoveHorizontal size={18} />,
  rect: <Square size={18} />,
  ellipse: <Circle size={18} />,
  triangle: <Triangle size={18} />,
  rhombus: <Diamond size={18} />,
  axes: <Move3d size={18} />,
};
const ACCESS_LABELS: Record<BoardAccess, string> = { none: "Не видят", read: "Только смотрят", edit: "Могут рисовать" };
const MIN_ZOOM = 0.1;
const MAX_ZOOM = 5;
const TEXT_SIZE = 20;

function chunks<T>(list: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size));
  return out;
}

export function BoardEditor({ initial }: { initial: Board }) {
  const [meta, setMeta] = useState<BoardSummary>(initial);
  const [role, setRole] = useState<BoardRole>(initial.role);
  const [items, setItems] = useState<Map<string, BoardItem>>(() => new Map(initial.items.map((i) => [i.id, i])));
  const [drafts, setDrafts] = useState<Map<string, { item: BoardItem; at: number }>>(() => new Map());
  const [view, setView] = useState<View>({ x: -40, y: -40, zoom: 1 });
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [tab, setTab] = useState<Tab>(initial.role === "read" ? "view" : "draw");
  const [tool, setTool] = useState<Tool>(initial.role === "read" ? "pan" : "pen");
  // На тёмной «школьной доске» по умолчанию пишем белым.
  const [color, setColor] = useState(initial.paper_color === "chalk" ? "#ffffff" : INKS[0]);
  const [sizeIdx, setSizeIdx] = useState(2);
  const [shape, setShape] = useState<ShapeKind>("line");
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [live, setLive] = useState<BoardItem | null>(null);
  const [lasso, setLasso] = useState<Pt[] | null>(null);
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(() => new Set());
  const [editingText, setEditingText] = useState<BoardItem | null>(null);
  const [formula, setFormula] = useState<{ item: BoardItem | null; latex: string } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [closed, setClosed] = useState<string | null>(null);
  const [historyLen, setHistoryLen] = useState({ undo: 0, redo: 0 });

  // «На всю вкладку» — доска поверх меню и шапки сайта; «Во весь экран» — полноэкранный режим браузера.
  const root = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  // На сервере — false; в браузере без полноэкранного режима (iPhone) кнопки нет.
  const canFullscreen = useSyncExternalStore(
    () => () => {},
    () => !!document.fullscreenEnabled,
    () => false,
  );
  useEffect(() => {
    const sync = () => setFullscreen(document.fullscreenElement === root.current && !!root.current);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);
  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
      return;
    }
    // Браузер не пустил в полный экран (встроенное окно, запрет) — хотя бы на всю вкладку.
    const fallback = setTimeout(() => !document.fullscreenElement && setExpanded(true), 1500);
    root.current
      ?.requestFullscreen()
      .then(() => clearTimeout(fallback))
      .catch(() => {
        clearTimeout(fallback);
        setExpanded(true);
      });
  }, []);
  // Esc сворачивает доску «на всю вкладку» (из полноэкранного режима браузер выводит сам).
  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !document.querySelector("dialog[open]") && setExpanded(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  const canEdit = role !== "read";
  const isOwner = role === "owner";
  const paperId = useId().replace(/:/g, "");
  const wrap = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const gesture = useRef<Gesture | null>(null);
  const touches = useRef(new Map<number, { x: number; y: number }>());
  const pinch = useRef<{ dist: number; cx: number; cy: number; view: View } | null>(null);
  const spaceDown = useRef(false);
  const history = useRef<{ undo: Ops[]; redo: Ops[] }>({ undo: [], redo: [] });
  // Актуальные значения для обработчиков событий.
  const viewRef = useRef(view);
  const itemsRef = useRef(items);
  useEffect(() => {
    viewRef.current = view;
    itemsRef.current = items;
  });

  // ---------- синхронизация ----------

  const onRemote = useCallback((e: Remote) => {
    if (e.type === "ops") {
      setItems((prev) => {
        const next = new Map(prev);
        for (const it of e.upsert) next.set(it.id, it);
        for (const id of e.delete) next.delete(id);
        return next;
      });
      setDrafts((prev) => {
        if (!prev.size) return prev;
        const next = new Map(prev);
        for (const it of e.upsert) next.delete(it.id);
        return next;
      });
    } else if (e.type === "draft") {
      setDrafts((prev) => new Map(prev).set(e.item.id, { item: e.item, at: Date.now() }));
    } else if (e.type === "board") {
      setMeta((m) => ({ ...m, ...e.board, role: e.role }));
      setRole(e.role);
      if (e.role === "read") {
        setTool("pan");
        setTab("view");
      }
    } else if (e.type === "reconnected") {
      whiteboard.get(initial.id).then((b) => setItems(new Map(b.items.map((i) => [i.id, i])))).catch(() => {});
    } else if (e.type === "closed") {
      setClosed(e.code === 4404 ? "Доску удалили." : "Педагог закрыл доступ к доске.");
    } else if (e.type === "error") {
      setMessage(e.message);
    }
  }, [initial.id]);
  const { status, send, sendDraft } = useBoardSync(initial.id, onRemote);

  // Черновики чужих штрихов, которые так и не дорисовали (обрыв связи), — убрать.
  useEffect(() => {
    const t = setInterval(() => {
      setDrafts((prev) => {
        const now = Date.now();
        const stale = [...prev].filter(([, d]) => now - d.at > 5000);
        if (!stale.length) return prev;
        const next = new Map(prev);
        for (const [id] of stale) next.delete(id);
        return next;
      });
    }, 2000);
    return () => clearInterval(t);
  }, []);

  const push = useCallback(
    (ops: Ops) => {
      for (const part of chunks(ops.upsert ?? [], 100)) send({ upsert: part });
      for (const part of chunks(ops.delete ?? [], 400)) send({ delete: part });
    },
    [send],
  );

  /** Своя правка: сразу на доске, на сервер и в историю (Ctrl+Z). */
  const commit = useCallback(
    (upsert: BoardItem[], remove: string[] = [], record = true) => {
      const prev = itemsRef.current;
      const undo: Ops = { upsert: [], delete: [] };
      for (const it of upsert) {
        const old = prev.get(it.id);
        if (old) undo.upsert!.push(old);
        else undo.delete!.push(it.id);
      }
      for (const id of remove) {
        const old = prev.get(id);
        if (old) undo.upsert!.push(old);
      }
      const next = new Map(prev);
      for (const it of upsert) next.set(it.id, it);
      for (const id of remove) next.delete(id);
      itemsRef.current = next;
      setItems(next);
      push({ upsert, delete: remove.filter((id) => prev.has(id)) });
      if (record) {
        history.current.undo.push(undo);
        history.current.redo = [];
        if (history.current.undo.length > 200) history.current.undo.shift();
        setHistoryLen({ undo: history.current.undo.length, redo: 0 });
      }
    },
    [push],
  );

  const replay = useCallback(
    (from: "undo" | "redo") => {
      const ops = history.current[from].pop();
      if (!ops) return;
      const prev = itemsRef.current;
      const inverse: Ops = { upsert: [], delete: [] };
      for (const it of ops.upsert ?? []) {
        const old = prev.get(it.id);
        if (old) inverse.upsert!.push(old);
        else inverse.delete!.push(it.id);
      }
      for (const id of ops.delete ?? []) {
        const old = prev.get(id);
        if (old) inverse.upsert!.push(old);
      }
      history.current[from === "undo" ? "redo" : "undo"].push(inverse);
      commit(ops.upsert ?? [], ops.delete ?? [], false);
      setSelected(new Set());
      setHistoryLen({ undo: history.current.undo.length, redo: history.current.redo.length });
    },
    [commit],
  );

  // ---------- размеры и координаты ----------

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setSize({ w: entry.contentRect.width, h: entry.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const toBoard = useCallback((clientX: number, clientY: number): [number, number] => {
    const rect = svg.current!.getBoundingClientRect();
    const v = viewRef.current;
    return [v.x + (clientX - rect.left) / v.zoom, v.y + (clientY - rect.top) / v.zoom];
  }, []);

  const zoomAt = useCallback((factor: number, clientX?: number, clientY?: number) => {
    const rect = svg.current?.getBoundingClientRect();
    setView((v) => {
      const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.zoom * factor));
      const sx = clientX !== undefined && rect ? clientX - rect.left : (rect?.width ?? 800) / 2;
      const sy = clientY !== undefined && rect ? clientY - rect.top : (rect?.height ?? 600) / 2;
      const bx = v.x + sx / v.zoom, by = v.y + sy / v.zoom;
      return { zoom, x: bx - sx / zoom, y: by - sy / zoom };
    });
  }, []);

  const fitAll = useCallback(() => {
    const box = union([...itemsRef.current.values()].map(bbox));
    if (!box) {
      setView({ x: -40, y: -40, zoom: 1 });
      return;
    }
    const pad = 40;
    const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.min(size.w / (box.w + 2 * pad), size.h / (box.h + 2 * pad), 1.5)));
    setView({ zoom, x: box.x - pad - (size.w / zoom - box.w - 2 * pad) / 2, y: box.y - pad - (size.h / zoom - box.h - 2 * pad) / 2 });
  }, [size]);

  // Колесо: прокрутка листа; с Ctrl/⌘ (и щипок на тачпаде) — масштаб.
  useEffect(() => {
    const el = svg.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) zoomAt(Math.exp(-e.deltaY * 0.01), e.clientX, e.clientY);
      else setView((v) => ({ ...v, x: v.x + e.deltaX / v.zoom, y: v.y + e.deltaY / v.zoom }));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  // ---------- инструменты ----------

  const strokeSize = (t: PenTool) => SIZES_MM[sizeIdx] * PX_PER_MM * TOOL_SCALE[t];
  const selectedItems = useMemo(() => [...selected].map((id) => items.get(id)).filter(Boolean) as BoardItem[], [selected, items]);
  const selBox = useMemo(() => union(selectedItems.map(bbox)), [selectedItems]);

  function itemAt(x: number, y: number): BoardItem | null {
    const r = 6 / viewRef.current.zoom;
    const list = [...itemsRef.current.values()].sort((a, b) => b.z - a.z);
    return list.find((it) => hits(it, x, y, r)) ?? null;
  }

  function onPointerDown(e: React.PointerEvent<SVGSVGElement>) {
    if (closed) return;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    if (e.pointerType === "touch") {
      touches.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (touches.current.size === 2) {
        // Два пальца — двигать и масштабировать лист; начатый штрих отменяется.
        gesture.current = null;
        setLive(null);
        const [a, b] = [...touches.current.values()];
        pinch.current = { dist: Math.hypot(a.x - b.x, a.y - b.y), cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2, view: viewRef.current };
        return;
      }
    }
    const [x, y] = toBoard(e.clientX, e.clientY);
    const panning = tool === "pan" || e.button === 1 || spaceDown.current || !canEdit;
    if (panning) {
      gesture.current = { kind: "pan", cx: e.clientX, cy: e.clientY, view: viewRef.current };
      return;
    }
    if (e.button !== 0) return;
    if (tool === "pen" || tool === "felt" || tool === "highlighter") {
      const pressure = e.pointerType === "pen" ? e.pressure || 0.5 : 0.5;
      const item: BoardItem = {
        id: newId(),
        kind: "stroke",
        z: Date.now(),
        data: { tool, color, size: strokeSize(tool), points: [[x, y, pressure]], simulate: e.pointerType !== "pen" },
      };
      gesture.current = { kind: "draw", item, sentAt: 0 };
      setLive(item);
    } else if (tool === "shape") {
      const item: BoardItem = {
        id: newId(),
        kind: "shape",
        z: Date.now(),
        data: { shape, color, size: Math.max(2, SIZES_MM[sizeIdx] * PX_PER_MM), x1: x, y1: y, x2: x, y2: y },
      };
      gesture.current = { kind: "shape", item };
      setLive(item);
    } else if (tool === "eraser") {
      gesture.current = { kind: "erase", ids: new Set() };
      eraseAt(x, y);
    } else if (tool === "text") {
      e.preventDefault(); // иначе щелчок по листу заберёт фокус у нового поля
      const hit = itemAt(x, y);
      if (hit?.kind === "text") setEditingText(hit);
      else
        setEditingText({ id: newId(), kind: "text", z: Date.now(), data: { x, y: y - TEXT_SIZE * 0.7, w: 320, h: TEXT_SIZE * 1.4, text: "", color, size: TEXT_SIZE } });
      setTool("select");
    } else if (tool === "select") {
      if (selBox && x >= selBox.x && x <= selBox.x + selBox.w && y >= selBox.y && y <= selBox.y + selBox.h) {
        gesture.current = { kind: "move", sx: x, sy: y, orig: selectedItems };
        return;
      }
      const hit = itemAt(x, y);
      if (hit) {
        setSelected(new Set([hit.id]));
        gesture.current = { kind: "move", sx: x, sy: y, orig: [hit] };
        return;
      }
      setSelected(new Set());
      gesture.current = { kind: "lasso", pts: [[x, y]] };
      setLasso([[x, y]]);
    }
  }

  function eraseAt(x: number, y: number) {
    const g = gesture.current;
    if (g?.kind !== "erase") return;
    const r = (SIZES_MM[sizeIdx] * PX_PER_MM * 2 + 4) / viewRef.current.zoom;
    let changed = false;
    for (const it of itemsRef.current.values()) {
      if (!g.ids.has(it.id) && hits(it, x, y, r)) {
        g.ids.add(it.id);
        changed = true;
      }
    }
    if (changed) setHiddenIds(new Set(g.ids));
  }

  function onPointerMove(e: React.PointerEvent<SVGSVGElement>) {
    if (e.pointerType === "touch" && touches.current.has(e.pointerId)) {
      touches.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
      const p = pinch.current;
      if (p && touches.current.size === 2) {
        const [a, b] = [...touches.current.values()];
        const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, p.view.zoom * (Math.hypot(a.x - b.x, a.y - b.y) / p.dist)));
        const rect = svg.current!.getBoundingClientRect();
        const bx = p.view.x + (p.cx - rect.left) / p.view.zoom, by = p.view.y + (p.cy - rect.top) / p.view.zoom;
        const cx = (a.x + b.x) / 2 - rect.left, cy = (a.y + b.y) / 2 - rect.top;
        setView({ zoom, x: bx - cx / zoom, y: by - cy / zoom });
        return;
      }
    }
    const g = gesture.current;
    if (!g) return;
    if (g.kind === "pan") {
      setView({ ...g.view, x: g.view.x - (e.clientX - g.cx) / g.view.zoom, y: g.view.y - (e.clientY - g.cy) / g.view.zoom });
      return;
    }
    const [x, y] = toBoard(e.clientX, e.clientY);
    if (g.kind === "draw") {
      const events = e.nativeEvent.getCoalescedEvents?.() ?? [e.nativeEvent];
      for (const ev of events) {
        const [px, py] = toBoard(ev.clientX, ev.clientY);
        g.item.data.points.push([px, py, ev.pointerType === "pen" ? ev.pressure || 0.5 : 0.5]);
      }
      g.item = { ...g.item, data: { ...g.item.data } };
      setLive(g.item);
      const now = Date.now();
      if (now - g.sentAt > 60) {
        g.sentAt = now;
        sendDraft(g.item);
      }
    } else if (g.kind === "shape") {
      g.item = { ...g.item, data: { ...g.item.data, x2: x, y2: y } };
      setLive(g.item);
    } else if (g.kind === "erase") {
      eraseAt(x, y);
    } else if (g.kind === "lasso") {
      g.pts.push([x, y]);
      setLasso([...g.pts]);
    } else if (g.kind === "move") {
      const moved = g.orig.map((it) => transform(it, x - g.sx, y - g.sy));
      setItems((prev) => {
        const next = new Map(prev);
        for (const it of moved) next.set(it.id, it);
        return next;
      });
    } else if (g.kind === "scale") {
      const sx = Math.max(0.05, (x - g.box.x) / g.box.w), sy = Math.max(0.05, (y - g.box.y) / g.box.h);
      const keep = g.orig.length === 1 && (g.orig[0].kind === "image" || g.orig[0].kind === "formula" || g.orig[0].kind === "text");
      const s = keep ? Math.max(sx, sy) : 0;
      const scaled = g.orig.map((it) => transform(it, 0, 0, keep ? s : sx, keep ? s : sy, g.box.x, g.box.y));
      setItems((prev) => {
        const next = new Map(prev);
        for (const it of scaled) next.set(it.id, it);
        return next;
      });
    }
  }

  function onPointerUp(e: React.PointerEvent<SVGSVGElement>) {
    if (e.pointerType === "touch") {
      touches.current.delete(e.pointerId);
      if (touches.current.size < 2) pinch.current = null;
    }
    const g = gesture.current;
    gesture.current = null;
    if (!g) return;
    if (g.kind === "draw" || g.kind === "shape") {
      setLive(null);
      const d = g.item.data;
      if (g.kind === "shape" && Math.hypot(d.x2 - d.x1, d.y2 - d.y1) < 3) return;
      commit([g.item]);
    } else if (g.kind === "erase") {
      setHiddenIds(new Set());
      if (g.ids.size) commit([], [...g.ids]);
    } else if (g.kind === "lasso") {
      setLasso(null);
      const ids = [...itemsRef.current.values()]
        .filter((it) => {
          const b = bbox(it);
          return inPolygon(b.x + b.w / 2, b.y + b.h / 2, g.pts);
        })
        .map((it) => it.id);
      setSelected(new Set(ids));
    } else if (g.kind === "move" || g.kind === "scale") {
      const now = g.orig.map((it) => itemsRef.current.get(it.id)).filter(Boolean) as BoardItem[];
      // Вернуть исходное в ссылку истории, затем записать перенос одной правкой.
      const restored = new Map(itemsRef.current);
      for (const it of g.orig) restored.set(it.id, it);
      itemsRef.current = restored;
      if (now.some((it, i) => it !== g.orig[i])) commit(now);
      else setItems(restored);
    }
  }

  // ---------- клавиатура и вставка ----------

  const deleteSelected = useCallback(() => {
    if (!selected.size) return;
    commit([], [...selected]);
    setSelected(new Set());
  }, [selected, commit]);

  useEffect(() => {
    const typing = (t: EventTarget | null) => t instanceof HTMLElement && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));
    const down = (e: KeyboardEvent) => {
      if (typing(e.target)) return;
      if (e.code === "Space") spaceDown.current = true;
      if (!canEdit) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.code === "KeyZ") {
        e.preventDefault();
        replay(e.shiftKey ? "redo" : "undo");
      } else if (mod && e.code === "KeyY") {
        e.preventDefault();
        replay("redo");
      } else if ((e.key === "Delete" || e.key === "Backspace") && selected.size) {
        e.preventDefault();
        deleteSelected();
      } else if (e.key === "Escape") {
        setSelected(new Set());
      }
    };
    const up = (e: KeyboardEvent) => {
      if (e.code === "Space") spaceDown.current = false;
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [canEdit, replay, selected, deleteSelected]);

  const viewCenter = useCallback((): [number, number] => {
    const v = viewRef.current;
    return [v.x + size.w / 2 / v.zoom, v.y + size.h / 2 / v.zoom];
  }, [size]);

  const insertImage = useCallback(
    async (file: File) => {
      setMessage(null);
      try {
        const local = URL.createObjectURL(file);
        const dims = await new Promise<{ w: number; h: number }>((resolve, reject) => {
          const img = new Image();
          img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight });
          img.onerror = () => reject(new Error("Не удалось прочитать картинку"));
          img.src = local;
        });
        URL.revokeObjectURL(local);
        const uploaded = await uploadFile(file, "content");
        const scale = Math.min(1, 600 / dims.w, 450 / dims.h);
        const [cx, cy] = viewCenter();
        const w = dims.w * scale, h = dims.h * scale;
        const item: BoardItem = { id: newId(), kind: "image", z: Date.now(), data: { x: cx - w / 2, y: cy - h / 2, w, h, file_id: uploaded.id } };
        commit([item]);
        setSelected(new Set([item.id]));
        setTool("select");
      } catch (e) {
        setMessage(errorText(e));
      }
    },
    [commit, viewCenter],
  );

  // Вставка снимка экрана или картинки из буфера (Ctrl+V).
  useEffect(() => {
    if (!canEdit) return;
    const onPaste = (e: ClipboardEvent) => {
      const t = e.target;
      if (t instanceof HTMLElement && (t.tagName === "TEXTAREA" || t.tagName === "INPUT")) return;
      const file = [...(e.clipboardData?.files ?? [])].find((f) => f.type.startsWith("image/"));
      if (file) {
        e.preventDefault();
        void insertImage(file);
        return;
      }
      const text = e.clipboardData?.getData("text/plain")?.trim();
      if (text) {
        e.preventDefault();
        const [cx, cy] = viewCenter();
        setEditingText({ id: newId(), kind: "text", z: Date.now(), data: { x: cx - 160, y: cy, w: 320, h: TEXT_SIZE * 1.4, text, color, size: TEXT_SIZE } });
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [canEdit, insertImage, viewCenter, color]);

  function saveText(item: BoardItem, text: string, height: number) {
    setEditingText(null);
    if (!text.trim()) {
      if (itemsRef.current.has(item.id)) commit([], [item.id]);
      return;
    }
    commit([{ ...item, data: { ...item.data, text, h: height } }]);
  }

  function saveFormula(latex: string) {
    const target = formula?.item;
    setFormula(null);
    if (!latex.trim()) return;
    const fontSize = target?.data.size ?? 24;
    const probe = document.createElement("div");
    probe.style.cssText = `position:absolute;visibility:hidden;white-space:nowrap;font-size:${fontSize}px`;
    probe.innerHTML = formulaHtml(latex);
    document.body.appendChild(probe);
    const w = probe.offsetWidth + 4, h = probe.offsetHeight + 4;
    probe.remove();
    if (target) {
      commit([{ ...target, data: { ...target.data, latex, w, h } }]);
      return;
    }
    const [cx, cy] = viewCenter();
    commit([{ id: newId(), kind: "formula", z: Date.now(), data: { x: cx - w / 2, y: cy - h / 2, w, h, latex, color, size: fontSize } }]);
  }

  function onDoubleClick(e: React.MouseEvent<SVGSVGElement>) {
    if (!canEdit) return;
    const [x, y] = toBoard(e.clientX, e.clientY);
    const hit = itemAt(x, y);
    if (hit?.kind === "text") setEditingText(hit);
    else if (hit?.kind === "formula") setFormula({ item: hit, latex: hit.data.latex });
  }

  function recolor(c: string) {
    setColor(c);
    if (!selectedItems.length) return;
    commit(selectedItems.filter((it) => it.kind !== "image").map((it) => ({ ...it, data: { ...it.data, color: c } })));
  }

  async function saveMeta(data: Parameters<typeof whiteboard.update>[1]) {
    setMessage(null);
    try {
      const out = await whiteboard.update(meta.id, data);
      setMeta(out);
    } catch (e) {
      setMessage(errorText(e));
    }
  }

  // ---------- отрисовка ----------

  const paper = PAPER_COLORS.find((p) => p.id === meta.paper_color) ?? PAPER_COLORS[0];
  const step = PAPER_STEP[meta.paper_style];
  const sorted = useMemo(() => [...items.values()].sort((a, b) => a.z - b.z), [items]);
  const remoteDrafts = [...drafts.values()].map((d) => d.item).filter((it) => !items.has(it.id));
  const cursor = closed
    ? "default"
    : !canEdit || tool === "pan"
      ? "grab"
      : tool === "select"
        ? "default"
        : tool === "text"
          ? "text"
          : tool === "eraser"
            ? "cell"
            : "crosshair";

  const toolButton = (id: Tool, label: string, icon: React.ReactNode) => (
    <RibbonButton active={tool === id} label={label} onClick={() => setTool(id)}>
      {icon}
    </RibbonButton>
  );

  return (
    <div
      ref={root}
      className={`flex flex-col overflow-hidden bg-surface ${
        fullscreen ? "h-full w-full" : expanded ? "fixed inset-0 z-50" : "h-[calc(100dvh-4rem)] rounded-2xl border border-line"
      }`}
    >
      {/* Заголовок */}
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2">
        <Link href="/dashboard/boards" className="text-sm text-fg-soft hover:text-fg">
          ← Доски
        </Link>
        {isOwner ? (
          <input
            defaultValue={meta.title}
            maxLength={200}
            aria-label="Название доски"
            onBlur={(e) => e.target.value.trim() && e.target.value.trim() !== meta.title && saveMeta({ title: e.target.value.trim() })}
            className="min-w-0 flex-1 rounded-lg bg-transparent px-2 py-1 font-semibold outline-none hover:bg-muted focus:bg-muted"
          />
        ) : (
          <span className="min-w-0 flex-1 truncate font-semibold">{meta.title}</span>
        )}
        <span className="text-xs text-fg-soft">
          {meta.target_title ? `${meta.target_title} · ` : ""}
          {isOwner ? `ученики: ${ACCESS_LABELS[meta.access].toLowerCase()}` : `${meta.owner_name}${role === "read" ? " · только просмотр" : ""}`}
        </span>
        {status !== "online" && (
          <span className="inline-flex items-center gap-1 text-xs text-danger" title="Правки сохранятся, когда связь восстановится">
            <WifiOff size={14} /> {status === "connecting" ? "Подключение…" : "Нет связи"}
          </span>
        )}
        {!fullscreen && (
          <button
            onClick={() => setExpanded((v) => !v)}
            title={expanded ? "Свернуть (Esc)" : "На всю вкладку"}
            aria-label={expanded ? "Свернуть" : "На всю вкладку"}
            aria-pressed={expanded}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2 text-sm text-fg-soft hover:bg-muted hover:text-fg"
          >
            {expanded ? <Shrink size={16} /> : <Expand size={16} />}
            <span className="hidden sm:inline">{expanded ? "Свернуть" : "На всю вкладку"}</span>
          </button>
        )}
        {canFullscreen && (
          <button
            onClick={toggleFullscreen}
            title={fullscreen ? "Выйти из полноэкранного режима (Esc)" : "Во весь экран"}
            aria-label={fullscreen ? "Выйти из полноэкранного режима" : "Во весь экран"}
            aria-pressed={fullscreen}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2 text-sm text-fg-soft hover:bg-muted hover:text-fg"
          >
            {fullscreen ? <Minimize size={16} /> : <Maximize size={16} />}
            <span className="hidden sm:inline">{fullscreen ? "Выйти" : "Во весь экран"}</span>
          </button>
        )}
      </div>

      {/* Лента: вкладки и инструменты, как в OneNote */}
      <div className="border-b border-line">
        <div className="flex gap-1 px-3 pt-1 text-sm">
          {canEdit && <TabButton active={tab === "draw"} onClick={() => setTab("draw")} label="Рисование" />}
          {canEdit && <TabButton active={tab === "insert"} onClick={() => setTab("insert")} label="Вставка" />}
          <TabButton active={tab === "view"} onClick={() => setTab("view")} label="Вид" />
        </div>
        <div className="flex min-h-[4.5rem] items-stretch gap-2 overflow-x-auto px-3 py-2">
          {tab === "draw" && canEdit && (
            <>
              <Group>
                {toolButton("select", "Выделение", <LassoSelect size={20} />)}
                {toolButton("pan", "Рука", <Hand size={20} />)}
                {toolButton("text", "Текст", <Type size={20} />)}
              </Group>
              <Group>
                {toolButton("eraser", "Ластик", <Eraser size={20} />)}
                {toolButton("pen", "Перо", <Pen size={20} />)}
                {toolButton("felt", "Фломастер", <Brush size={20} />)}
                {toolButton("highlighter", "Маркер", <Highlighter size={20} />)}
              </Group>
              <Group>
                <div className="flex items-center gap-1.5">
                  {INKS.map((c) => (
                    <button
                      key={c}
                      onClick={() => recolor(c)}
                      aria-label={`Цвет ${c}`}
                      aria-pressed={color === c}
                      className={`h-7 w-7 rounded-full border ${color === c ? "ring-2 ring-brand ring-offset-2 ring-offset-surface" : "border-line"}`}
                      style={{ background: c }}
                    />
                  ))}
                  <label className="relative h-7 w-7 cursor-pointer overflow-hidden rounded-full border border-line" title="Другой цвет">
                    <span className="absolute inset-0" style={{ background: "conic-gradient(red, yellow, lime, cyan, blue, magenta, red)" }} />
                    <input type="color" value={color} onChange={(e) => recolor(e.target.value)} className="absolute inset-0 cursor-pointer opacity-0" />
                  </label>
                </div>
              </Group>
              <Group>
                {SIZES_MM.map((mm, i) => (
                  <RibbonButton key={mm} active={sizeIdx === i} label={`${String(mm).replace(".", ",")} мм`} onClick={() => setSizeIdx(i)}>
                    <svg width="34" height="20" viewBox="0 0 34 20">
                      <path d="M3 15 C 10 2, 16 2, 18 10 S 27 18, 31 4" fill="none" stroke={color === "#ffffff" ? "currentColor" : color} strokeWidth={0.8 + i * 0.9} strokeLinecap="round" />
                    </svg>
                  </RibbonButton>
                ))}
              </Group>
              <Group>
                <RibbonButton label="Отменить" disabled={!historyLen.undo} onClick={() => replay("undo")}>
                  <Undo2 size={20} />
                </RibbonButton>
                <RibbonButton label="Вернуть" disabled={!historyLen.redo} onClick={() => replay("redo")}>
                  <Redo2 size={20} />
                </RibbonButton>
                {selected.size > 0 && (
                  <RibbonButton label="Удалить" onClick={deleteSelected}>
                    <Trash2 size={20} />
                  </RibbonButton>
                )}
              </Group>
            </>
          )}
          {tab === "insert" && canEdit && (
            <>
              <Group>
                {toolButton("text", "Текст", <Type size={20} />)}
                <RibbonButton label="Рисунок" onClick={() => fileInput.current?.click()}>
                  <ImagePlus size={20} />
                </RibbonButton>
                <RibbonButton label="Формула" onClick={() => setFormula({ item: null, latex: "" })}>
                  <Sigma size={20} />
                </RibbonButton>
                <input
                  ref={fileInput}
                  type="file"
                  accept="image/png,image/jpeg,image/gif,image/webp"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    e.target.value = "";
                    if (f) void insertImage(f);
                  }}
                />
              </Group>
              <Group>
                <div className="grid grid-cols-4 gap-1">
                  {SHAPES.map((s) => (
                    <button
                      key={s.id}
                      title={s.label}
                      aria-label={s.label}
                      aria-pressed={tool === "shape" && shape === s.id}
                      onClick={() => {
                        setShape(s.id);
                        setTool("shape");
                      }}
                      className={`flex h-8 w-8 items-center justify-center rounded-lg text-brand ${tool === "shape" && shape === s.id ? "bg-brand/15 ring-1 ring-brand" : "hover:bg-muted"}`}
                    >
                      {SHAPE_ICONS[s.id]}
                    </button>
                  ))}
                </div>
              </Group>
              <p className="self-center text-xs text-fg-soft">Снимок экрана или картинку можно вставить из буфера — Ctrl+V (⌘V).</p>
            </>
          )}
          {tab === "view" && (
            <>
              <Group>
                <RibbonButton label="Уменьшить" onClick={() => zoomAt(1 / 1.25)}>
                  <ZoomOut size={20} />
                </RibbonButton>
                <RibbonButton label="Увеличить" onClick={() => zoomAt(1.25)}>
                  <ZoomIn size={20} />
                </RibbonButton>
                <div className="flex flex-col justify-center gap-1 text-sm">
                  <button className="rounded-md px-2 py-0.5 text-left hover:bg-muted" onClick={() => setView((v) => ({ ...v, zoom: 1 }))}>
                    {Math.round(view.zoom * 100)}% · 100%
                  </button>
                  <button className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-left hover:bg-muted" onClick={fitAll}>
                    <Maximize2 size={14} /> Показать всё
                  </button>
                </div>
                {!canEdit && toolButton("pan", "Рука", <Hand size={20} />)}
              </Group>
              {isOwner && (
                <>
                  <Group>
                    <label className="flex flex-col justify-center gap-1 text-xs text-fg-soft">
                      Стиль бумаги
                      <select
                        value={meta.paper_style}
                        onChange={(e) => saveMeta({ paper_style: e.target.value as PaperStyle })}
                        className="h-9 rounded-lg border border-line bg-surface px-2 text-sm text-fg"
                      >
                        {PAPER_STYLES.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="flex flex-col justify-center gap-1 text-xs text-fg-soft">
                      Цвет бумаги
                      <div className="flex gap-1">
                        {PAPER_COLORS.map((p) => (
                          <button
                            key={p.id}
                            title={p.label}
                            aria-label={p.label}
                            aria-pressed={meta.paper_color === p.id}
                            onClick={() => {
                              if (p.id === "chalk" && color === "#000000") setColor("#ffffff");
                              if (p.id !== "chalk" && color === "#ffffff") setColor("#000000");
                              void saveMeta({ paper_color: p.id as PaperColor });
                            }}
                            className={`h-7 w-7 rounded-md border border-line ${meta.paper_color === p.id ? "ring-2 ring-brand" : ""}`}
                            style={{ background: p.bg }}
                          />
                        ))}
                      </div>
                    </div>
                  </Group>
                  <Group>
                    <label className="flex flex-col justify-center gap-1 text-xs text-fg-soft">
                      Ученикам {meta.target_title ? `(${meta.target_title})` : ""}
                      <select
                        value={meta.access}
                        onChange={(e) => saveMeta({ access: e.target.value as BoardAccess })}
                        className="h-9 rounded-lg border border-line bg-surface px-2 text-sm text-fg"
                      >
                        {(Object.keys(ACCESS_LABELS) as BoardAccess[]).map((a) => (
                          <option key={a} value={a}>
                            {ACCESS_LABELS[a]}
                          </option>
                        ))}
                      </select>
                    </label>
                  </Group>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {message && (
        <div className="px-4 pt-2">
          <Alert>{message}</Alert>
        </div>
      )}

      {/* Лист */}
      <div ref={wrap} className="relative min-h-0 flex-1 overflow-hidden" style={{ background: paper.bg }}>
        {closed ? (
          <div className="flex h-full items-center justify-center p-6 text-center">
            <div className="space-y-3 rounded-2xl bg-surface p-6 shadow">
              <p className="font-medium">{closed}</p>
              <Link href="/dashboard/boards" className="text-sm text-brand hover:underline">
                К списку досок
              </Link>
            </div>
          </div>
        ) : (
          <svg
            ref={svg}
            width={size.w}
            height={size.h}
            className="block touch-none select-none"
            style={{ cursor }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onDoubleClick={onDoubleClick}
          >
            <defs>
              {step > 0 && (
                <pattern id={paperId} width={step} height={step} patternUnits="userSpaceOnUse">
                  {meta.paper_style.startsWith("lines") && <path d={`M 0 ${step - 0.5} H ${step}`} stroke={paper.line} strokeWidth={1} />}
                  {meta.paper_style.startsWith("grid") && <path d={`M ${step - 0.5} 0 V ${step} M 0 ${step - 0.5} H ${step}`} stroke={paper.line} strokeWidth={0.8} fill="none" />}
                  {meta.paper_style === "dots" && <circle cx={step / 2} cy={step / 2} r={1.3} fill={paper.line} />}
                </pattern>
              )}
            </defs>
            <g transform={`scale(${view.zoom}) translate(${-view.x} ${-view.y})`}>
              {step > 0 && <rect x={view.x} y={view.y} width={size.w / view.zoom} height={size.h / view.zoom} fill={`url(#${paperId})`} />}
              {sorted.map((it) => (
                <ItemView key={it.id} item={it} hidden={hiddenIds.has(it.id) || editingText?.id === it.id} />
              ))}
              {remoteDrafts.map((it) => (
                <ItemView key={`d-${it.id}`} item={it} />
              ))}
              {live && <ItemView item={live} />}
              {lasso && (
                <polyline
                  points={lasso.map(([x, y]) => `${x},${y}`).join(" ")}
                  fill="rgba(99,102,241,0.08)"
                  stroke="#6366f1"
                  strokeWidth={1.2 / view.zoom}
                  strokeDasharray={`${4 / view.zoom} ${3 / view.zoom}`}
                />
              )}
              {selBox && canEdit && (
                <g>
                  <rect
                    x={selBox.x - 4 / view.zoom}
                    y={selBox.y - 4 / view.zoom}
                    width={selBox.w + 8 / view.zoom}
                    height={selBox.h + 8 / view.zoom}
                    fill="rgba(99,102,241,0.04)"
                    stroke="#6366f1"
                    strokeWidth={1.2 / view.zoom}
                    strokeDasharray={`${5 / view.zoom} ${3 / view.zoom}`}
                    style={{ cursor: "move" }}
                  />
                  <rect
                    x={selBox.x + selBox.w}
                    y={selBox.y + selBox.h}
                    width={12 / view.zoom}
                    height={12 / view.zoom}
                    fill="#ffffff"
                    stroke="#6366f1"
                    strokeWidth={1.5 / view.zoom}
                    style={{ cursor: "nwse-resize" }}
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      (e.target as Element).setPointerCapture(e.pointerId);
                      gesture.current = { kind: "scale", box: selBox, orig: selectedItems };
                    }}
                  />
                </g>
              )}
            </g>
          </svg>
        )}
        {editingText && (
          <TextEditor key={editingText.id} item={editingText} view={view} onDone={(text, h) => saveText(editingText, text, h)} />
        )}
      </div>

      <Modal open={!!formula} onClose={() => setFormula(null)} title="Формула">
        {formula && <FormulaForm initial={formula.latex} onSave={saveFormula} />}
      </Modal>
    </div>
  );
}

function TextEditor({ item, view, onDone }: { item: BoardItem; view: View; onDone: (text: string, height: number) => void }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [text, setText] = useState<string>(item.data.text);
  const fit = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  };
  useEffect(() => {
    fit();
    const t = setTimeout(() => ref.current?.focus(), 30);
    return () => clearTimeout(t);
  }, []);
  const d = item.data;
  return (
    <textarea
      ref={ref}
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        fit();
      }}
      onBlur={() => onDone(text, (ref.current?.scrollHeight ?? d.size * 1.4 * view.zoom) / view.zoom)}
      onKeyDown={(e) => e.key === "Escape" && ref.current?.blur()}
      placeholder="Текст"
      className="absolute resize-none overflow-hidden rounded border border-brand bg-transparent p-0 outline-none"
      style={{
        left: (d.x - view.x) * view.zoom,
        top: (d.y - view.y) * view.zoom,
        width: d.w * view.zoom,
        fontSize: d.size * view.zoom,
        lineHeight: 1.35,
        color: d.color,
      }}
    />
  );
}

function FormulaForm({ initial, onSave }: { initial: string; onSave: (latex: string) => void }) {
  const [latex, setLatex] = useState(initial);
  const input = useRef<HTMLTextAreaElement>(null);
  // Окно при открытии ставит фокус на свою первую кнопку — поле формулы фокусируем после него.
  useEffect(() => {
    const t = setTimeout(() => input.current?.focus(), 50);
    return () => clearTimeout(t);
  }, []);
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(latex);
      }}
    >
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">Формула в LaTeX</span>
        <textarea
          ref={input}
          rows={3}
          value={latex}
          onChange={(e) => setLatex(e.target.value)}
          placeholder="x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}"
          className="w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 font-mono text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
      </label>
      <div className="min-h-12 overflow-x-auto rounded-xl bg-muted px-3 py-3 text-xl" dangerouslySetInnerHTML={{ __html: formulaHtml(latex) }} />
      <Button type="submit" className="w-full" disabled={!latex.trim()}>
        Вставить
      </Button>
    </form>
  );
}

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`border-b-2 px-3 py-1.5 font-medium ${active ? "border-brand text-fg" : "border-transparent text-fg-soft hover:text-fg"}`}
    >
      {label}
    </button>
  );
}

function Group({ children }: { children: React.ReactNode }) {
  return <div className="flex shrink-0 items-stretch gap-1 border-r border-line pr-2 last:border-0">{children}</div>;
}

function RibbonButton({
  active,
  disabled,
  label,
  onClick,
  children,
}: {
  active?: boolean;
  disabled?: boolean;
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={`flex min-w-14 flex-col items-center justify-center gap-1 rounded-lg px-2 py-1 text-xs disabled:opacity-40 ${active ? "bg-brand/15 text-fg ring-1 ring-brand" : "text-fg-soft hover:bg-muted hover:text-fg"}`}
    >
      {children}
      <span className="whitespace-nowrap">{label}</span>
    </button>
  );
}
