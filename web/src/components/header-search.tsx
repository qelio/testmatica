"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { createSearcher, MIN_QUERY, normalize, searchPlaceholder, type SearchResult } from "@/lib/search";

const DEBOUNCE_MS = 250;

/** Совпадение с запросом выделено цветом. */
function Highlight({ text, query }: { text: string; query: string }) {
  const at = normalize(text).indexOf(normalize(query));
  if (at < 0) return text;
  return (
    <>
      {text.slice(0, at)}
      <b className="font-semibold text-brand-text">{text.slice(at, at + query.length)}</b>
      {text.slice(at + query.length)}
    </>
  );
}

export function HeaderSearch({ roles }: { roles: string[] }) {
  const router = useRouter();
  const key = roles.join(",");
  // eslint-disable-next-line react-hooks/exhaustive-deps -- состав ролей задан строкой key
  const searcher = useMemo(() => createSearcher(roles), [key]);

  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const mac = useSyncExternalStore(
    () => () => {},
    () => /Mac|iPhone|iPad/.test(navigator.platform),
    () => true,
  );

  const query = text.trim();
  const ready = query.length >= MIN_QUERY;
  // Устаревшие результаты не показываем: они относятся к другому запросу.
  const current = ready && result?.query === query ? result : null;
  const flat = current?.groups.flatMap((g) => g.hits) ?? [];

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      void searcher.search(query).then((r) => {
        if (!cancelled) setResult(r);
      });
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [ready, query, searcher]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // В текстовом редакторе сочетание остаётся за редактором.
      if (e.key.toLowerCase() !== "k" && e.code !== "KeyK") return;
      if (!(e.metaKey || e.ctrlKey) || (e.target as HTMLElement).isContentEditable) return;
      e.preventDefault();
      setOpen(true);
      searcher.warm();
      // На телефоне поле появляется только после открытия.
      requestAnimationFrame(() => input.current?.focus());
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [searcher]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function finish() {
    setOpen(false);
    setText("");
    setActive(0);
    input.current?.blur();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      setOpen(false);
      input.current?.blur();
    } else if (e.key === "ArrowDown" && flat.length) {
      e.preventDefault();
      setActive((active + 1) % flat.length);
    } else if (e.key === "ArrowUp" && flat.length) {
      e.preventDefault();
      setActive((active - 1 + flat.length) % flat.length);
    } else if (e.key === "Enter" && flat[active]) {
      e.preventDefault();
      router.push(flat[active].href);
      finish();
    }
  }

  let index = -1;
  const showPanel = open && ready;

  return (
    // На телефоне поле раскрывается под шапкой во всю ширину, на широком экране стоит по центру.
    <div ref={root} className="flex min-w-0 flex-1 justify-end md:justify-center">
      <button
        type="button"
        className="grid h-10 w-10 shrink-0 place-items-center rounded-xl text-fg-soft hover:bg-muted hover:text-fg md:hidden"
        aria-label="Поиск"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
          searcher.warm();
          requestAnimationFrame(() => input.current?.focus());
        }}
      >
        <Search size={20} strokeWidth={1.8} aria-hidden />
      </button>
      <div
        className={`md:relative md:block md:w-full md:max-w-md ${open ? "absolute top-full right-3 left-3 mt-2 md:top-auto md:right-auto md:left-auto md:mt-0" : "hidden"}`}
      >
        <label className="flex h-10 items-center gap-2.5 rounded-xl bg-muted px-3 text-fg-soft focus-within:bg-surface focus-within:outline-2 focus-within:outline-brand max-md:bg-surface max-md:shadow-lg max-md:outline max-md:outline-line">
          <Search size={18} strokeWidth={1.9} aria-hidden className="shrink-0" />
          <input
            ref={input}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setActive(0);
              setOpen(true);
            }}
            onFocus={() => {
              setOpen(true);
              searcher.warm();
            }}
            onKeyDown={onKeyDown}
            maxLength={100}
            placeholder={searchPlaceholder(roles)}
            aria-label="Поиск по кабинету"
            role="combobox"
            aria-expanded={showPanel}
            aria-controls={listId}
            aria-activedescendant={flat[active] ? `${listId}-${active}` : undefined}
            autoComplete="off"
            className="min-w-0 flex-1 bg-transparent text-sm text-fg outline-none placeholder:text-fg-soft"
          />
          <kbd className="hidden shrink-0 rounded-md border border-line bg-surface px-1.5 py-0.5 font-sans text-[11px] font-semibold md:block">
            {open ? "Esc" : mac ? "⌘K" : "Ctrl K"}
          </kbd>
        </label>
        {showPanel && (
          <div
            id={listId}
            role="listbox"
            aria-label="Результаты поиска"
            className="mt-2 max-h-[min(30rem,calc(100dvh-9rem))] overflow-y-auto rounded-xl border border-line bg-surface pb-2 shadow-lg md:absolute md:inset-x-0 md:top-full"
          >
            {!current && <p className="px-4 pt-4 pb-2 text-sm text-fg-soft">Ищем…</p>}
            {current?.failed === "all" && <p className="px-4 pt-4 pb-2 text-sm text-danger">Не удалось выполнить поиск</p>}
            {current && current.failed !== "all" && flat.length === 0 && (
              <p className="px-4 pt-4 pb-2 text-sm text-fg-soft">Ничего не найдено</p>
            )}
            {current?.groups.map((group) => (
              <div key={group.title} role="presentation">
                <p className="px-4 pt-3 pb-1 text-[11px] font-semibold tracking-wider text-fg-soft uppercase">{group.title}</p>
                {group.hits.map((hit) => {
                  index += 1;
                  const i = index;
                  const Icon = group.icon;
                  return (
                    <Link
                      key={hit.href}
                      id={`${listId}-${i}`}
                      href={hit.href}
                      role="option"
                      aria-selected={i === active}
                      onClick={finish}
                      onMouseEnter={() => setActive(i)}
                      className={`flex items-center gap-3 px-4 py-2 ${i === active ? "bg-muted" : ""}`}
                    >
                      <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg text-fg-soft ${i === active ? "bg-surface" : "bg-muted"}`}>
                        <Icon size={18} strokeWidth={1.9} aria-hidden />
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium">
                          <Highlight text={hit.title} query={query} />
                        </span>
                        {hit.sub && <span className="block truncate text-xs text-fg-soft">{hit.sub}</span>}
                      </span>
                    </Link>
                  );
                })}
              </div>
            ))}
            {current?.failed === "some" && <p className="px-4 pt-3 text-xs text-fg-soft">Часть результатов не загрузилась</p>}
          </div>
        )}
      </div>
    </div>
  );
}
