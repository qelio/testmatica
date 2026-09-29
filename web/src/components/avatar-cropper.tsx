"use client";

import { RotateCcw, RotateCw, Undo2, ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Alert, Button, Modal } from "@/components/ui";

const FRAME = 280; // сторона рамки на экране, px
const OUT = 512; // сторона итогового фото, px
const MAX_ZOOM = 5;
const MAX_INPUT = 20 * 1024 * 1024; // исходник может быть большим — в хранилище уйдёт уже обрезанный квадрат
const ACCEPT = "image/png,image/jpeg,image/webp";

type View = { x: number; y: number; z: number; r: number }; // сдвиг центра, масштаб (1 — фото закрывает рамку), поворот
const START: View = { x: 0, y: 0, z: 1, r: 0 };

/** Кнопка выбора фото профиля: после выбора — окно кадрирования, наружу отдаётся готовый квадрат JPEG. */
export function AvatarUploadButton({
  onCropped,
  label,
  disabled,
  className = "cursor-pointer rounded-xl border border-line px-4 py-2 text-sm font-medium hover:bg-muted",
}: {
  onCropped: (file: File) => void;
  label: string;
  disabled?: boolean;
  className?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string>();
  return (
    <>
      <button type="button" disabled={disabled} onClick={() => input.current?.click()} className={`${className} disabled:opacity-50`}>
        {label}
      </button>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (!f) return;
          if (!ACCEPT.split(",").includes(f.type)) return setError("Подойдёт фото в формате JPG, PNG или WebP");
          if (f.size > MAX_INPUT) return setError("Файл больше 20 МБ — выберите фото поменьше");
          setError(undefined);
          setFile(f);
        }}
      />
      {error && (
        <div className="basis-full">
          <Alert>{error}</Alert>
        </div>
      )}
      <Modal open={file !== null} onClose={() => setFile(null)} title="Фото профиля">
        {file && (
          <Cropper
            file={file}
            onCancel={() => setFile(null)}
            onDone={(cropped) => {
              setFile(null);
              onCropped(cropped);
            }}
          />
        )}
      </Modal>
    </>
  );
}

function Cropper({ file, onCancel, onDone }: { file: File; onCancel: () => void; onDone: (f: File) => void }) {
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [error, setError] = useState<string>();
  const [view, setView] = useState<View>(START);
  const frame = useRef<HTMLDivElement>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const pinch = useRef<number | null>(null);

  useEffect(() => {
    let alive = true; // после размонтирования ссылка отозвана — её ошибку не показываем
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => alive && setImg(image);
    image.onerror = () => alive && setError("Не удалось открыть фото — попробуйте другой файл");
    image.src = url;
    return () => {
      alive = false;
      URL.revokeObjectURL(url);
    };
  }, [file]);

  // Размер фото на экране при данном масштабе и повороте; сдвиг ограничен так, чтобы рамка всегда была закрыта фото.
  const fit = useCallback(
    (v: View): View => {
      if (!img) return v;
      const z = Math.min(MAX_ZOOM, Math.max(1, v.z));
      const [w, h] = v.r % 180 ? [img.naturalHeight, img.naturalWidth] : [img.naturalWidth, img.naturalHeight];
      const scale = (FRAME / Math.min(w, h)) * z;
      const mx = (w * scale - FRAME) / 2;
      const my = (h * scale - FRAME) / 2;
      return {
        ...v,
        z,
        x: Math.min(mx, Math.max(-mx, v.x)),
        y: Math.min(my, Math.max(-my, v.y)),
      };
    },
    [img],
  );

  /** Масштаб относительно точки (px от центра рамки): точка под курсором остаётся на месте. */
  const zoomAt = useCallback(
    (factor: number, px = 0, py = 0) =>
      setView((v) => {
        const z = Math.min(MAX_ZOOM, Math.max(1, v.z * factor));
        const k = z / v.z;
        return fit({ ...v, z, x: px - (px - v.x) * k, y: py - (py - v.y) * k });
      }),
    [fit],
  );

  // Колесо мыши — масштаб; слушатель не пассивный, чтобы не прокручивать страницу.
  useEffect(() => {
    const el = frame.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const b = el.getBoundingClientRect();
      zoomAt(Math.exp(-e.deltaY * 0.0015), e.clientX - b.left - FRAME / 2, e.clientY - b.top - FRAME / 2);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt, img]);

  function distance() {
    const [a, b] = [...pointers.current.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  function onPointerMove(e: React.PointerEvent) {
    const prev = pointers.current.get(e.pointerId);
    if (!prev) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 2) {
      // Два пальца — масштаб щипком относительно середины между ними.
      const d = distance();
      if (pinch.current) {
        const b = frame.current!.getBoundingClientRect();
        const [a, c] = [...pointers.current.values()];
        zoomAt(d / pinch.current, (a.x + c.x) / 2 - b.left - FRAME / 2, (a.y + c.y) / 2 - b.top - FRAME / 2);
      }
      pinch.current = d;
      return;
    }
    setView((v) => fit({ ...v, x: v.x + e.clientX - prev.x, y: v.y + e.clientY - prev.y }));
  }

  function onKeyDown(e: React.KeyboardEvent) {
    const step = e.shiftKey ? 30 : 8;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [step, 0],
      ArrowRight: [-step, 0],
      ArrowUp: [0, step],
      ArrowDown: [0, -step],
    };
    if (moves[e.key]) {
      e.preventDefault();
      const [dx, dy] = moves[e.key];
      setView((v) => fit({ ...v, x: v.x + dx, y: v.y + dy }));
    } else if (e.key === "+" || e.key === "=") zoomAt(1.1);
    else if (e.key === "-") zoomAt(1 / 1.1);
  }

  const rotate = (dir: 1 | -1) => setView((v) => fit({ ...v, r: (v.r + dir * 90 + 360) % 360 }));

  async function save() {
    if (!img) return;
    const scale = (FRAME / Math.min(img.naturalWidth, img.naturalHeight)) * view.z * (OUT / FRAME);
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = OUT;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#fff"; // прозрачный PNG в JPEG — на белом фоне
    ctx.fillRect(0, 0, OUT, OUT);
    ctx.imageSmoothingQuality = "high";
    ctx.translate(OUT / 2 + view.x * (OUT / FRAME), OUT / 2 + view.y * (OUT / FRAME));
    ctx.rotate((view.r * Math.PI) / 180);
    const [dw, dh] = [img.naturalWidth * scale, img.naturalHeight * scale];
    ctx.drawImage(img, -dw / 2, -dh / 2, dw, dh);
    const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/jpeg", 0.9));
    if (!blob) return setError("Не удалось подготовить фото — попробуйте ещё раз");
    onDone(new File([blob], "avatar.jpg", { type: "image/jpeg" }));
  }

  if (error) return <Alert>{error}</Alert>;
  const scale = img ? (FRAME / Math.min(img.naturalWidth, img.naturalHeight)) * view.z : 1;

  return (
    <div className="space-y-4">
      <div
        ref={frame}
        tabIndex={0}
        role="application"
        aria-label="Рамка фото: перетаскивайте, колесо или щипок — масштаб, стрелки — сдвиг, + и − — масштаб"
        onKeyDown={onKeyDown}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
          pinch.current = pointers.current.size === 2 ? distance() : null;
        }}
        onPointerMove={onPointerMove}
        onPointerUp={(e) => {
          pointers.current.delete(e.pointerId);
          pinch.current = null;
        }}
        onPointerCancel={(e) => {
          pointers.current.delete(e.pointerId);
          pinch.current = null;
        }}
        className="relative mx-auto cursor-grab touch-none overflow-hidden rounded-xl bg-muted outline-none select-none focus-visible:ring-2 focus-visible:ring-brand active:cursor-grabbing"
        style={{ width: FRAME, height: FRAME }}
      >
        {img && (
          // Предпросмотр локального файла — обычный img.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={img.src}
            alt=""
            draggable={false}
            className="pointer-events-none absolute top-1/2 left-1/2 max-w-none"
            style={{
              width: img.naturalWidth * scale,
              height: img.naturalHeight * scale,
              transform: `translate(-50%, -50%) translate(${view.x}px, ${view.y}px) rotate(${view.r}deg)`,
            }}
          />
        )}
        {/* Круг — так фото будет выглядеть в кабинете и анкете; углы тоже сохранятся. */}
        <div className="pointer-events-none absolute inset-0 rounded-full border-2 border-white/80 shadow-[0_0_0_200px_rgb(0_0_0/0.45)]" />
      </div>

      <div className="flex items-center gap-2">
        <button type="button" onClick={() => zoomAt(1 / 1.2)} className="rounded-lg p-2 text-fg-soft hover:bg-muted" aria-label="Уменьшить">
          <ZoomOut size={18} />
        </button>
        <input
          type="range"
          min={1}
          max={MAX_ZOOM}
          step={0.01}
          value={view.z}
          onChange={(e) => zoomAt(Number(e.target.value) / view.z)}
          aria-label="Масштаб"
          className="min-w-0 flex-1 accent-brand"
        />
        <button type="button" onClick={() => zoomAt(1.2)} className="rounded-lg p-2 text-fg-soft hover:bg-muted" aria-label="Увеличить">
          <ZoomIn size={18} />
        </button>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-1">
        <button
          type="button"
          onClick={() => rotate(-1)}
          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-fg-soft hover:bg-muted"
        >
          <RotateCcw size={16} /> Повернуть влево
        </button>
        <button
          type="button"
          onClick={() => rotate(1)}
          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-fg-soft hover:bg-muted"
        >
          <RotateCw size={16} /> Вправо
        </button>
        <button
          type="button"
          onClick={() => setView(START)}
          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-fg-soft hover:bg-muted"
        >
          <Undo2 size={16} /> Сбросить
        </button>
      </div>
      <p className="text-center text-xs text-fg-soft">Перетащите фото, чтобы выбрать кадр. Масштаб — колесом мыши, щипком или ползунком.</p>
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel}>
          Отмена
        </Button>
        <Button onClick={save} disabled={!img}>
          Сохранить
        </Button>
      </div>
    </div>
  );
}
