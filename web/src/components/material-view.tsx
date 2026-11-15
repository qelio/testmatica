"use client";

import { BookOpen, ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

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
export function MaterialView({ material, n, onFavorite, onStudied, onSolved, numbered = false }: {
  material: Material;
  n?: number;
  numbered?: boolean;
  onFavorite?: (on: boolean) => void;
  onStudied?: (id: string) => void;
  onSolved?: (id: string) => void;
}) {
  const { status } = useAuth();
  const signedIn = status === "authenticated";
  const [favorite, setFavorite] = useState(material.favorite);
  const article = useRef<HTMLElement>(null);
  const bodyId = useId();
  const toggle = useRef<HTMLButtonElement>(null);
  const [expanded, setExpanded] = useState<boolean>();
  const collapsible = numbered && material.kind === "card";
  const showBody = !collapsible || (expanded ?? !material.collapsed_by_default);

  useEffect(() => {
    if (expanded !== undefined) toggle.current?.focus({ preventScroll: true });
  }, [expanded]);

  useEffect(() => {
    if (!signedIn || material.viewed || material.kind === "video") return;
    if (!onStudied) {
      content.saveProgress(material.id).catch(() => {});
      return;
    }
    const element = article.current;
    if (!element) return;
    let saving = false;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting || saving) return;
      saving = true;
      content.saveProgress(material.id).then(() => {
        observer.disconnect();
        onStudied(material.id);
      }).catch(() => { saving = false; });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [signedIn, material.id, material.viewed, material.kind, onStudied]);

  const yt = material.kind === "link" && material.url ? youtubeId(material.url) : null;

  return (
    <article ref={article} className={`tm-card rounded-2xl border bg-surface ${showBody ? "p-5 sm:p-6" : ""} ${material.kind === "card" && showBody ? "border-brand/40" : "border-line"}`}>
      {!showBody && (
        <button
          type="button"
          ref={toggle}
          onClick={() => setExpanded(true)}
          aria-label="Развернуть теоретическую карточку"
          aria-expanded={false}
          aria-controls={bodyId}
          className="flex min-h-15 w-full items-center justify-between gap-3 rounded-[inherit] px-4 py-2 text-left hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fg-soft sm:px-5"
        >
          <span className="flex min-w-0 items-center gap-3 text-sm font-semibold">
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-muted text-fg-soft">
              <BookOpen size={16} aria-hidden="true" />
            </span>
            Теоретическая карточка
          </span>
          <span aria-hidden="true" className="flex shrink-0 items-center gap-1.5 text-sm text-fg-soft">
            <span className="hidden sm:inline">Развернуть</span>
            <ChevronDown size={16} />
          </span>
        </button>
      )}
      {showBody && (
        <header className="mb-4 flex items-start justify-between gap-2">
          <div className="flex items-center gap-4">
            {n !== undefined && <span className="tm-only tm-num">{n}</span>}
            <div>
              <Badge tone={material.kind === "card" ? "brand" : "neutral"}>{KIND_LABELS[material.kind]}</Badge>
              <h2 className="mt-1 text-xl font-semibold leading-snug">{material.title}</h2>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {collapsible && (
              <button
                type="button"
                ref={toggle}
                onClick={() => setExpanded(false)}
                aria-expanded={true}
                aria-controls={bodyId}
                className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-medium text-fg-soft hover:bg-muted hover:text-fg"
              >
                <ChevronDown size={16} aria-hidden="true" className="rotate-180" />
                Свернуть
              </button>
            )}
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
          </div>
        </header>
      )}

      {(material.kind === "text" || material.kind === "card") && (
        <div id={bodyId} hidden={!showBody}>{showBody && <Markdown text={material.body} />}</div>
      )}
      {material.kind === "task" && material.task_id && <TaskSolver taskId={material.task_id} contextId={material.id} onSolved={onSolved} compact={numbered} />}
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
            className="inline-flex items-center gap-2 rounded-xl border border-line px-4 py-2.5 font-medium text-brand-text hover:bg-muted"
          >
            Открыть ссылку ↗<span className="max-w-72 truncate text-sm font-normal text-fg-soft">{new URL(material.url).hostname}</span>
          </a>
        )
      )}
    </article>
  );
}
