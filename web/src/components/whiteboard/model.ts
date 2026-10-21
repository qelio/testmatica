/** Доска (решение №60): объекты в координатах доски (бесконечный лист), их рамки, сдвиг, масштаб и попадание. */

import { getStroke } from "perfect-freehand";

import type { BoardItem, PaperColor, PaperStyle } from "@/lib/api";

export type Pt = [number, number, number?];
export type Box = { x: number; y: number; w: number; h: number };

export type PenTool = "pen" | "felt" | "highlighter";
export type ShapeKind = "line" | "arrow" | "arrow2" | "rect" | "ellipse" | "triangle" | "rhombus" | "axes";

export type StrokeData = { tool: PenTool; color: string; size: number; points: Pt[] };
export type ShapeData = { shape: ShapeKind; color: string; size: number; x1: number; y1: number; x2: number; y2: number };
export type TextData = { x: number; y: number; w: number; h: number; text: string; color: string; size: number };
export type FormulaData = { x: number; y: number; w: number; h: number; latex: string; color: string; size: number };
export type ImageData = { x: number; y: number; w: number; h: number; file_id: string };

/** Толщина как в OneNote (мм) → пиксели доски при масштабе 100%. */
export const SIZES_MM = [0.25, 0.35, 0.5, 0.7, 1];
export const PX_PER_MM = 4;
export const TOOL_SCALE: Record<PenTool, number> = { pen: 1, felt: 2.5, highlighter: 8 };
export const INKS = ["#000000", "#2563eb", "#16a34a", "#dc2626", "#ea580c", "#9333ea", "#0891b2", "#ffffff"];

export const PAPER_STYLES: { id: PaperStyle; label: string }[] = [
  { id: "plain", label: "Без линий" },
  { id: "lines_narrow", label: "Узкая линейка" },
  { id: "lines", label: "Линейка" },
  { id: "lines_wide", label: "Широкая линейка" },
  { id: "grid_small", label: "Мелкая клетка" },
  { id: "grid", label: "Клетка" },
  { id: "grid_big", label: "Крупная клетка" },
  { id: "dots", label: "Точки" },
];
export const PAPER_COLORS: { id: PaperColor; label: string; bg: string; line: string }[] = [
  { id: "white", label: "Белая", bg: "#ffffff", line: "#c9d6e8" },
  { id: "cream", label: "Кремовая", bg: "#fdf8ec", line: "#e2d6b8" },
  { id: "yellow", label: "Жёлтая", bg: "#fff9c4", line: "#e6d98a" },
  { id: "blue", label: "Голубая", bg: "#e8f1fb", line: "#b9cde6" },
  { id: "green", label: "Зелёная", bg: "#eaf6ea", line: "#bcd9bc" },
  { id: "pink", label: "Розовая", bg: "#fdeef2", line: "#ebc4cf" },
  { id: "gray", label: "Серая", bg: "#f1f2f4", line: "#cfd3da" },
  { id: "chalk", label: "Школьная доска", bg: "#24392f", line: "#3f5a4c" },
];
export const PAPER_STEP: Record<PaperStyle, number> = {
  plain: 0, lines_narrow: 24, lines: 32, lines_wide: 44, grid_small: 20, grid: 32, grid_big: 48, dots: 24,
};

export const SHAPES: { id: ShapeKind; label: string }[] = [
  { id: "line", label: "Линия" },
  { id: "arrow", label: "Стрелка" },
  { id: "arrow2", label: "Двойная стрелка" },
  { id: "rect", label: "Прямоугольник" },
  { id: "ellipse", label: "Эллипс" },
  { id: "triangle", label: "Треугольник" },
  { id: "rhombus", label: "Ромб" },
  { id: "axes", label: "Оси координат" },
];

/** Контур штриха: перо — с нажимом, фломастер — ровный, маркер — широкий полупрозрачный. */
export function strokePath(d: StrokeData, simulate = false): string {
  const flat = d.tool !== "pen";
  const outline = getStroke(d.points as number[][], {
    size: d.size,
    thinning: flat ? 0 : 0.55,
    smoothing: 0.5,
    streamline: 0.45,
    simulatePressure: simulate && !flat,
    last: true,
  });
  if (!outline.length) return "";
  if (outline.length < 3) {
    const [x, y] = outline[0];
    const r = d.size / 2;
    return `M ${x - r} ${y} a ${r} ${r} 0 1 0 ${2 * r} 0 a ${r} ${r} 0 1 0 ${-2 * r} 0`;
  }
  let path = `M ${outline[0][0].toFixed(1)} ${outline[0][1].toFixed(1)} Q`;
  for (let i = 0; i < outline.length; i++) {
    const [x0, y0] = outline[i];
    const [x1, y1] = outline[(i + 1) % outline.length];
    path += ` ${x0.toFixed(1)} ${y0.toFixed(1)} ${((x0 + x1) / 2).toFixed(1)} ${((y0 + y1) / 2).toFixed(1)}`;
  }
  return path + " Z";
}

export function bbox(item: BoardItem): Box {
  const d = item.data;
  if (item.kind === "stroke") {
    const pts = (d as StrokeData).points;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const [x, y] of pts) {
      minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
    }
    const r = (d as StrokeData).size / 2;
    return { x: minX - r, y: minY - r, w: maxX - minX + 2 * r, h: maxY - minY + 2 * r };
  }
  if (item.kind === "shape") {
    const s = d as ShapeData;
    const r = s.size / 2 + (s.shape.startsWith("arrow") || s.shape === "axes" ? 8 : 0);
    return { x: Math.min(s.x1, s.x2) - r, y: Math.min(s.y1, s.y2) - r, w: Math.abs(s.x2 - s.x1) + 2 * r, h: Math.abs(s.y2 - s.y1) + 2 * r };
  }
  return { x: d.x, y: d.y, w: d.w, h: d.h };
}

export function union(boxes: Box[]): Box | null {
  if (!boxes.length) return null;
  const x = Math.min(...boxes.map((b) => b.x)), y = Math.min(...boxes.map((b) => b.y));
  const r = Math.max(...boxes.map((b) => b.x + b.w)), btm = Math.max(...boxes.map((b) => b.y + b.h));
  return { x, y, w: r - x, h: btm - y };
}

/** Сдвинуть и растянуть относительно точки (ox, oy): x' = ox + (x − ox)·sx + dx. */
export function transform(item: BoardItem, dx: number, dy: number, sx = 1, sy = 1, ox = 0, oy = 0): BoardItem {
  const fx = (x: number) => ox + (x - ox) * sx + dx;
  const fy = (y: number) => oy + (y - oy) * sy + dy;
  const d = item.data;
  if (item.kind === "stroke") {
    return { ...item, data: { ...d, points: (d as StrokeData).points.map(([x, y, p]) => [fx(x), fy(y), p]) } };
  }
  if (item.kind === "shape") {
    return { ...item, data: { ...d, x1: fx(d.x1), y1: fy(d.y1), x2: fx(d.x2), y2: fy(d.y2) } };
  }
  const scale = item.kind === "text" || item.kind === "formula" ? Math.sqrt(Math.abs(sx * sy)) : 1;
  return {
    ...item,
    data: { ...d, x: fx(d.x), y: fy(d.y), w: d.w * Math.abs(sx), h: d.h * Math.abs(sy), ...(d.size ? { size: d.size * scale } : {}) },
  };
}

function segDist(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const vx = bx - ax, vy = by - ay;
  const len = vx * vx + vy * vy;
  const t = len ? Math.max(0, Math.min(1, ((px - ax) * vx + (py - ay) * vy) / len)) : 0;
  return Math.hypot(px - (ax + t * vx), py - (ay + t * vy));
}

function shapeSegments(s: ShapeData): [number, number, number, number][] {
  const { x1, y1, x2, y2 } = s;
  const l = Math.min(x1, x2), r = Math.max(x1, x2), t = Math.min(y1, y2), b = Math.max(y1, y2);
  const cx = (l + r) / 2, cy = (t + b) / 2;
  switch (s.shape) {
    case "rect":
      return [[l, t, r, t], [r, t, r, b], [r, b, l, b], [l, b, l, t]];
    case "triangle":
      return [[cx, t, r, b], [r, b, l, b], [l, b, cx, t]];
    case "rhombus":
      return [[cx, t, r, cy], [r, cy, cx, b], [cx, b, l, cy], [l, cy, cx, t]];
    case "axes":
      return [[l, cy, r, cy], [cx, b, cx, t]];
    case "ellipse": {
      const out: [number, number, number, number][] = [];
      const rx = (r - l) / 2, ry = (b - t) / 2;
      for (let i = 0; i < 32; i++) {
        const a = (i / 32) * Math.PI * 2, c = ((i + 1) / 32) * Math.PI * 2;
        out.push([cx + rx * Math.cos(a), cy + ry * Math.sin(a), cx + rx * Math.cos(c), cy + ry * Math.sin(c)]);
      }
      return out;
    }
    default:
      return [[x1, y1, x2, y2]];
  }
}

/** Попадание в объект (ластик, выбор щелчком): у штрихов и фигур — близко к линии, у остальных — внутри рамки. */
export function hits(item: BoardItem, x: number, y: number, radius: number): boolean {
  const b = bbox(item);
  if (x < b.x - radius || x > b.x + b.w + radius || y < b.y - radius || y > b.y + b.h + radius) return false;
  if (item.kind === "stroke") {
    const d = item.data as StrokeData;
    const pts = d.points;
    const r = radius + d.size / 2;
    if (pts.length === 1) return Math.hypot(pts[0][0] - x, pts[0][1] - y) <= r;
    for (let i = 1; i < pts.length; i++) if (segDist(x, y, pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]) <= r) return true;
    return false;
  }
  if (item.kind === "shape") {
    const s = item.data as ShapeData;
    return shapeSegments(s).some(([ax, ay, bx, by]) => segDist(x, y, ax, ay, bx, by) <= radius + s.size / 2);
  }
  return true;
}

/** Точка внутри многоугольника (произвольное выделение). */
export function inPolygon(x: number, y: number, poly: Pt[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export const newId = () => crypto.randomUUID();
export const imageUrl = (fileId: string) => `/api/media/files/${fileId}/content`;
