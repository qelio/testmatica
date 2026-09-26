"use client";

import { useState } from "react";

import { OfferCard } from "@/components/offers";
import { Alert, EmptyState, Select, Spinner } from "@/components/ui";
import { content, marketplace } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LEVEL_LABELS } from "@/lib/format";
import { useLoad } from "@/lib/hooks";

/** Каталог наборов в группы: занятия в мини-группе у репетитора. Закрытые группы сюда не попадают. */
export default function GroupsPage() {
  const { status } = useAuth();
  const authed = status === "authenticated";
  const subjects = useLoad(() => content.subjects(), []);
  const [filters, setFilters] = useState<{ subject_id: string; level: string; price_max: number | "" }>({ subject_id: "", level: "", price_max: "" });
  const offers = useLoad(() => marketplace.offers(filters, authed), [filters.subject_id, filters.level, filters.price_max, authed]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Группы</h1>
        <p className="mt-1 text-fg-soft">Занятия в мини-группе у репетитора. Группа стартует, когда наберётся минимум учеников.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Select label="Предмет" value={filters.subject_id} onChange={(e) => setFilters({ ...filters, subject_id: e.target.value })}>
          <option value="">Все</option>
          {subjects.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
        <Select label="Для кого" value={filters.level} onChange={(e) => setFilters({ ...filters, level: e.target.value })}>
          <option value="">Все</option>
          {Object.entries(LEVEL_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
        <Select label="Цена за занятие" value={String(filters.price_max)} onChange={(e) => setFilters({ ...filters, price_max: e.target.value ? Number(e.target.value) : "" })}>
          <option value="">Любая</option>
          <option value="0">Бесплатно</option>
          <option value="500">до 500 ₽</option>
          <option value="1000">до 1 000 ₽</option>
          <option value="2000">до 2 000 ₽</option>
        </Select>
      </div>
      {offers.error && <Alert>{offers.error}</Alert>}
      {!offers.data ? (
        !offers.error && <Spinner />
      ) : offers.data.length ? (
        <div className="grid gap-4 md:grid-cols-2">
          {offers.data.map((o) => (
            <OfferCard key={o.id} offer={o} />
          ))}
        </div>
      ) : (
        <EmptyState title="Подходящих групп пока нет" text="Попробуйте другой предмет или загляните позже." />
      )}
    </div>
  );
}
