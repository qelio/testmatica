"use client";

import { useState } from "react";

import { TutorCardView } from "@/components/tutor-card";
import { Alert, Button, EmptyState, Field, Select, Spinner } from "@/components/ui";
import { content, marketplace, type TutorCard, type TutorSearch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { FORMAT_LABELS, LEVEL_LABELS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";

export default function TutorsPage() {
  const { status } = useAuth();
  const subjects = useLoad(() => content.subjects(), []);
  const [filters, setFilters] = useState<TutorSearch>({ sort: "rating" });
  const [q, setQ] = useState("");
  const [extra, setExtra] = useState<TutorCard[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string>();
  const authed = status === "authenticated";
  const page = useLoad(() => marketplace.search(filters, authed), [filters, authed]);
  const set = (patch: Partial<TutorSearch>) => {
    setExtra([]);
    setFilters((f) => ({ ...f, ...patch }));
  };
  const items = [...(page.data?.items ?? []), ...extra];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Найти репетитора</h1>
        <p className="mt-1 text-fg-soft">Занятия проходят на платформе: видеосвязь, задания, оплата. Контакты репетиторов не публикуются.</p>
      </div>

      <div className="grid gap-3 rounded-2xl border border-line bg-surface p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Select label="Предмет" value={filters.subject_id ?? ""} onChange={(e) => set({ subject_id: e.target.value || undefined })}>
          <option value="">Любой</option>
          {subjects.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
        <Select label="Уровень ученика" value={filters.level ?? ""} onChange={(e) => set({ level: e.target.value as TutorSearch["level"] })}>
          <option value="">Любой</option>
          {Object.entries(LEVEL_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
        <Select label="Формат" value={filters.format ?? ""} onChange={(e) => set({ format: e.target.value as TutorSearch["format"] })}>
          <option value="">Любой</option>
          {Object.entries(FORMAT_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
        <Select label="Рейтинг" value={String(filters.min_rating ?? "")} onChange={(e) => set({ min_rating: e.target.value ? Number(e.target.value) : "" })}>
          <option value="">Любой</option>
          <option value="9">от 9</option>
          <option value="8">от 8</option>
          <option value="7">от 7</option>
        </Select>
        <div className="grid grid-cols-2 gap-2">
          <Field
            label="Цена от, ₽"
            type="number"
            min={0}
            step={100}
            value={filters.price_min ?? ""}
            onChange={(e) => set({ price_min: e.target.value ? Number(e.target.value) : "" })}
          />
          <Field
            label="до, ₽"
            type="number"
            min={0}
            step={100}
            value={filters.price_max ?? ""}
            onChange={(e) => set({ price_max: e.target.value ? Number(e.target.value) : "" })}
          />
        </div>
        <form
          className="sm:col-span-2"
          onSubmit={(e) => {
            e.preventDefault();
            set({ q: q.trim() || undefined });
          }}
        >
          <Field label="Поиск" type="search" placeholder="Имя или о чём занятия" value={q} onChange={(e) => setQ(e.target.value)} />
        </form>
        <div className="flex flex-col justify-end gap-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={!!filters.verified} onChange={(e) => set({ verified: e.target.checked })} className="h-4 w-4 accent-brand" />
            Образование подтверждено
          </label>
          <Select label="Сортировка" value={filters.sort} onChange={(e) => set({ sort: e.target.value as TutorSearch["sort"] })}>
            <option value="rating">По рейтингу</option>
            <option value="price_asc">Сначала дешевле</option>
            <option value="price_desc">Сначала дороже</option>
            <option value="new">Новые</option>
          </Select>
        </div>
      </div>

      {(page.error || error) && <Alert>{page.error || error}</Alert>}
      {!page.data ? (
        !page.error && <Spinner />
      ) : !items.length ? (
        <EmptyState title="Никого не нашли" text="Попробуйте убрать часть фильтров." />
      ) : (
        <>
          <p className="text-sm text-fg-soft">Найдено: {page.data.total}</p>
          <ul className="space-y-3">
            {items.map((t) => (
              <li key={t.user_id}>
                <TutorCardView tutor={t} />
              </li>
            ))}
          </ul>
          {items.length < page.data.total && (
            <Button
              variant="secondary"
              loading={loadingMore}
              onClick={async () => {
                setLoadingMore(true);
                try {
                  const next = await marketplace.search({ ...filters, offset: items.length }, authed);
                  setExtra((x) => [...x, ...next.items]);
                } catch (e) {
                  setError(errorText(e));
                } finally {
                  setLoadingMore(false);
                }
              }}
            >
              Показать ещё
            </Button>
          )}
        </>
      )}
    </div>
  );
}
