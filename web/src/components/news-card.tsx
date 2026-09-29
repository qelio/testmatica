import Link from "next/link";

import type { NewsSummary } from "@/lib/server-api";

export function fmtNewsDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" }) : "";
}

export function NewsCard({ news }: { news: NewsSummary }) {
  return (
    <Link href={`/news/${news.slug}`} className="group overflow-hidden rounded-2xl border border-line bg-surface hover:border-brand/50">
      {news.cover_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={news.cover_url} alt="" className="aspect-[16/9] w-full object-cover" />
      ) : (
        <div className="aspect-[16/9] w-full bg-gradient-to-br from-brand/20 to-brand/5" />
      )}
      <div className="space-y-1.5 p-4">
        <p className="text-xs text-fg-soft">{fmtNewsDate(news.published_at)}</p>
        <h3 className="font-semibold group-hover:text-brand">{news.title}</h3>
        {news.summary && <p className="text-sm text-fg-soft">{news.summary}</p>}
      </div>
    </Link>
  );
}

