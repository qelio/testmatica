"use client";

import { useEffect, useId, useRef, useState } from "react";

import { whiteboard, type BoardSummary } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

import { ItemView } from "./items";
import { bbox, PAPER_COLORS, PAPER_STEP, union } from "./model";

export function BoardThumbnail({ board }: { board: BoardSummary }) {
  const target = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const patternId = useId();

  useEffect(() => {
    if (!target.current || !board.items_count) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: "160px" });
    observer.observe(target.current);
    return () => observer.disconnect();
  }, [board.items_count]);

  const { data, error } = useLoad(
    () => visible && board.items_count ? whiteboard.get(board.id) : Promise.resolve(null),
    [visible, board.id, board.items_count, board.updated_at],
  );
  const paper = PAPER_COLORS.find((color) => color.id === board.paper_color) ?? PAPER_COLORS[0];
  const style = board.paper_style;
  const step = PAPER_STEP[style];
  const items = data && !error && board.items_count ? [...data.items].sort((a, b) => a.z - b.z) : [];
  const bounds = union(items.map(bbox).filter(({ x, y, w, h }) => [x, y, w, h].every(Number.isFinite)));
  // Вписываем всё содержимое и оставляем поля вокруг объектов.
  const width = Math.max(180, (bounds?.w ?? 0) * 1.12, (bounds?.h ?? 0) * 2);
  const height = width * 9 / 16;
  const x = bounds ? bounds.x + (bounds.w - width) / 2 : 0;
  const y = bounds ? bounds.y + (bounds.h - height) / 2 : 0;

  return (
    <div ref={target} className="relative aspect-video overflow-hidden border-b border-line" style={{ backgroundColor: paper.bg }}>
      <svg aria-hidden="true" className="block size-full" viewBox={`${x} ${y} ${width} ${height}`}>
        {step > 0 && (
          <>
            <defs>
              <pattern id={patternId} width={step} height={step} patternUnits="userSpaceOnUse">
                {style.startsWith("lines") && <path d={`M 0 ${step - 0.5} H ${step}`} stroke={paper.line} />}
                {style.startsWith("grid") && <path d={`M ${step - 0.5} 0 V ${step} M 0 ${step - 0.5} H ${step}`} stroke={paper.line} strokeWidth={0.8} fill="none" />}
                {style === "dots" && <circle cx={step / 2} cy={step / 2} r={1.3} fill={paper.line} />}
              </pattern>
            </defs>
            <rect x={x} y={y} width={width} height={height} fill={`url(#${patternId})`} />
          </>
        )}
        {items.map((item) => <ItemView key={item.id} item={item} />)}
      </svg>
      {(!board.items_count || error) && (
        <div className="absolute inset-0 grid place-items-center">
          <span className="rounded-full bg-surface px-3 py-1 text-xs text-fg-soft">
            {error ? "Предпросмотр недоступен" : "Пустая доска"}
          </span>
        </div>
      )}
    </div>
  );
}
