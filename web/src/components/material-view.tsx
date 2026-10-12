"use client";

import { useEffect, useRef, useState } from "react";

import { AttachmentView } from "@/components/files";
import { Markdown } from "@/components/markdown";
import { TaskSolver } from "@/components/task-solver";
import { Badge } from "@/components/ui";
import { content, type Material } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export const KIND_LABELS: Record<Material["kind"], string> = {
  text: "Текст",
  card: "Теоретическая карточка",
  video: "Видео",
  pdf: "PDF",
  file: "Документ",
  link: "Ссылка",
  task: "Задача",
};

/** Встраивание YouTube по ссылке вида youtube.com/watch?v=… или youtu.be/… */
function youtubeId(url: string): string | null {
  try {
    const u = new URL(url);
    if (u.hostname === "youtu.be") return u.pathname.slice(1) || null;
    if (u.hostname.endsWith("youtube.com")) return u.searchParams.get("v") ?? (u.pathname.startsWith("/embed/") ? u.pathname.split("/")[2] : null);
  } catch {}
  return null;
}

function VideoPlayer({ material, signedIn }: { material: Material; signedIn: boolean }) {
  const ref = useRef<HTMLVideoElement>(null);
  const lastSaved = useRef(material.position_sec);

  useEffect(() => {
    const video = ref.current;
    if (!video || !signedIn) return;
    // Продолжить с того места, где ученик остановился.
    const start = () => {
      if (material.position_sec > 0 && material.position_sec < video.duration - 5) video.currentTime = material.position_sec;
    };
    const save = () => {
      const pos = Math.floor(video.currentTime);
      if (Math.abs(pos - lastSaved.current) >= 10 || video.paused || video.ended) {
        lastSaved.current = pos;
        content.saveProgress(material.id, pos).catch(() => {});
      }
    };
    video.addEventListener("loadedmetadata", start);
    video.addEventListener("timeupdate", save);
    video.addEventListener("pause", save);
    return () => {
      video.removeEventListener("loadedmetadata", start);
      video.removeEventListener("timeupdate", save);
      video.removeEventListener("pause", save);
    };
  }, [material.id, material.position_sec, signedIn]);

  if (!material.file?.url) return <p className="text-sm text-fg-soft">Видео временно недоступно.</p>;
  return (
    <video ref={ref} src={material.file.url} controls preload="metadata" className="w-full rounded-xl bg-black">
      Ваш браузер не поддерживает видео.
    </video>
  );
}

/** n — номер материала в модуле: виден в игровых оформлениях курса (кружок у заголовка). */
export function MaterialView({ material, n, onFavorite }: { material: Material; n?: number; onFavorite?: (on: boolean) => void }) {
  const { status } = useAuth();
  const signedIn = status === "authenticated";
  const [favorite, setFavorite] = useState(material.favorite);

  // Открыл — значит просмотрел (для видео — позиция сохраняется плеером).
  useEffect(() => {
    if (signedIn && !material.viewed && material.kind !== "video") content.saveProgress(material.id).catch(() => {});
  }, [signedIn, material.id, material.viewed, material.kind]);

  const yt = material.kind === "link" && material.url ? youtubeId(material.url) : null;

  return (
    <article className={`tm-card rounded-2xl border bg-surface p-5 sm:p-6 ${material.kind === "card" ? "border-brand/40" : "border-line"}`}>
      <header className="mb-4 flex items-start justify-between gap-3">
        <div className="flex items-center gap-4">
          {n !== undefined && <span className="tm-only tm-num">{n}</span>}
          <div>
            <Badge tone={material.kind === "card" ? "brand" : "neutral"}>{KIND_LABELS[material.kind]}</Badge>
            <h2 className="mt-1 text-xl font-semibold leading-snug">{material.title}</h2>
          </div>
        </div>
        {signedIn && (
          <button
            onClick={() => {
              const on = !favorite;
              setFavorite(on);
              content.favorite(material.id, on).catch(() => setFavorite(!on));
              onFavorite?.(on);
            }}
            aria-pressed={favorite}
            aria-label={favorite ? "Убрать из избранного" : "В избранное"}
            title={favorite ? "Убрать из избранного" : "В избранное"}
            className={`text-2xl leading-none ${favorite ? "text-tutor" : "text-fg-soft hover:text-fg"}`}
          >
            {favorite ? "★" : "☆"}
          </button>
        )}
      </header>

      {(material.kind === "text" || material.kind === "card") && <Markdown text={material.body} />}
      {material.kind === "task" && material.task_id && <TaskSolver taskId={material.task_id} contextId={material.id} />}
      {material.kind === "video" && <VideoPlayer material={material} signedIn={signedIn} />}
      {material.kind === "pdf" && material.file?.url && (
        <iframe src={material.file.url} title={material.title} className="h-[75vh] w-full rounded-xl border border-line" />
      )}
      {material.kind === "file" && material.file && (
        <AttachmentView att={{ ...material.file, size: material.file.size ?? 0 }} />
      )}
      {material.kind === "link" && material.url && (
        yt ? (
          <div className="aspect-video overflow-hidden rounded-xl bg-black">
            <iframe
              src={`https://www.youtube-nocookie.com/embed/${yt}`}
              title={material.title}
              allow="accelerometer; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
              className="h-full w-full"
            />
          </div>
        ) : (
          <a
            href={material.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-xl border border-line px-4 py-2.5 font-medium text-brand hover:bg-muted"
          >
            Открыть ссылку ↗<span className="max-w-72 truncate text-sm font-normal text-fg-soft">{new URL(material.url).hostname}</span>
          </a>
        )
      )}
    </article>
  );
}
