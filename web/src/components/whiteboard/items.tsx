"use client";

import "katex/dist/katex.min.css";

import katex from "katex";
import { memo, useMemo } from "react";

import type { BoardItem } from "@/lib/api";

import { type FormulaData, imageUrl, type ImageData, type ShapeData, strokePath, type StrokeData, type TextData } from "./model";

function arrowHead(x1: number, y1: number, x2: number, y2: number, size: number): string {
  const a = Math.atan2(y2 - y1, x2 - x1);
  const len = 8 + size * 2;
  const p = (da: number) => `${x2 - len * Math.cos(a + da)} ${y2 - len * Math.sin(a + da)}`;
  return `M ${p(0.45)} L ${x2} ${y2} L ${p(-0.45)}`;
}

export function shapePath(s: ShapeData): string {
  const { x1, y1, x2, y2 } = s;
  const l = Math.min(x1, x2), r = Math.max(x1, x2), t = Math.min(y1, y2), b = Math.max(y1, y2);
  const cx = (l + r) / 2, cy = (t + b) / 2;
  switch (s.shape) {
    case "rect":
      return `M ${l} ${t} H ${r} V ${b} H ${l} Z`;
    case "ellipse":
      return `M ${l} ${cy} A ${(r - l) / 2} ${(b - t) / 2} 0 1 0 ${r} ${cy} A ${(r - l) / 2} ${(b - t) / 2} 0 1 0 ${l} ${cy} Z`;
    case "triangle":
      return `M ${cx} ${t} L ${r} ${b} L ${l} ${b} Z`;
    case "rhombus":
      return `M ${cx} ${t} L ${r} ${cy} L ${cx} ${b} L ${l} ${cy} Z`;
    case "axes":
      return `M ${l} ${cy} H ${r} ${arrowHead(l, cy, r, cy, s.size)} M ${cx} ${b} V ${t} ${arrowHead(cx, b, cx, t, s.size)}`;
    case "arrow":
      return `M ${x1} ${y1} L ${x2} ${y2} ${arrowHead(x1, y1, x2, y2, s.size)}`;
    case "arrow2":
      return `M ${x1} ${y1} L ${x2} ${y2} ${arrowHead(x1, y1, x2, y2, s.size)} ${arrowHead(x2, y2, x1, y1, s.size)}`;
    default:
      return `M ${x1} ${y1} L ${x2} ${y2}`;
  }
}

export function formulaHtml(latex: string): string {
  if (!latex.trim()) return "";
  try {
    return katex.renderToString(latex, { throwOnError: false, displayMode: false, output: "html" });
  } catch {
    return latex;
  }
}

/** Один объект доски. memo — штрих не пересчитывается, пока не изменился. */
export const ItemView = memo(function ItemView({ item, hidden }: { item: BoardItem; hidden?: boolean }) {
  const d = item.data;
  const path = useMemo(() => (item.kind === "stroke" ? strokePath(d as StrokeData, !!d.simulate) : ""), [item.kind, d]);
  const html = useMemo(() => (item.kind === "formula" ? formulaHtml((d as FormulaData).latex) : ""), [item.kind, d]);
  if (hidden) return null;
  switch (item.kind) {
    case "stroke": {
      const s = d as StrokeData;
      return <path d={path} fill={s.color} opacity={s.tool === "highlighter" ? 0.35 : 1} />;
    }
    case "shape": {
      const s = d as ShapeData;
      return <path d={shapePath(s)} fill="none" stroke={s.color} strokeWidth={s.size} strokeLinecap="round" strokeLinejoin="round" />;
    }
    case "text": {
      const t = d as TextData;
      return (
        <foreignObject x={t.x} y={t.y} width={Math.max(t.w, 20)} height={Math.max(t.h, t.size * 1.4)} style={{ overflow: "visible" }}>
          <div style={{ color: t.color, fontSize: t.size, lineHeight: 1.35, whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontFamily: "inherit" }}>
            {t.text}
          </div>
        </foreignObject>
      );
    }
    case "formula": {
      const f = d as FormulaData;
      return (
        <foreignObject x={f.x} y={f.y} width={Math.max(f.w, 20)} height={Math.max(f.h, 20)} style={{ overflow: "visible" }}>
          <div style={{ color: f.color, fontSize: f.size, whiteSpace: "nowrap" }} dangerouslySetInnerHTML={{ __html: html }} />
        </foreignObject>
      );
    }
    case "image": {
      const im = d as ImageData;
      return <image href={imageUrl(im.file_id)} x={im.x} y={im.y} width={im.w} height={im.h} preserveAspectRatio="none" />;
    }
  }
});
