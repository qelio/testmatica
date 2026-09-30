import type { Metadata } from "next";

import { NewsCard } from "@/components/news-card";
import type { NewsSummary } from "@/lib/server-api";
import { serverGet } from "@/lib/server-api";

export const metadata: Metadata = { title: "Новости — ТестМатика" };

/** Лента новостей (ведёт администратор). */
export default async function NewsPage() {
  const page = await serverGet<{ items: NewsSummary[]; total: number }>("/api/content/site/news?limit=50");
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Новости</h1>
      {!page ? (
        <p className="text-fg-soft">Не удалось загрузить новости. Попробуйте обновить страницу.</p>
      ) : page.items.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {page.items.map((n) => (
            <NewsCard key={n.id} news={n} />
          ))}
        </div>
      ) : (
        <p className="text-fg-soft">Новостей пока нет.</p>
      )}
    </div>
  );
}
