"use client";

/** Постраничный вывод: «Назад» / «Вперёд» и номер страницы. hasNext — пришло больше, чем помещается на страницу. */
export function Pager({ page, hasNext, onPage }: { page: number; hasNext: boolean; onPage: (page: number) => void }) {
  if (page === 0 && !hasNext) return null;
  const btn = "rounded-xl border border-line px-4 py-2 text-sm font-medium hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40";
  return (
    <nav className="flex items-center justify-center gap-3" aria-label="Страницы">
      <button type="button" className={btn} disabled={page === 0} onClick={() => onPage(page - 1)}>
        ← Назад
      </button>
      <span className="text-sm text-fg-soft tabular-nums">Страница {page + 1}</span>
      <button type="button" className={btn} disabled={!hasNext} onClick={() => onPage(page + 1)}>
        Вперёд →
      </button>
    </nav>
  );
}
