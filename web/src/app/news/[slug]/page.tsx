import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Markdown } from "@/components/markdown";
import { fmtNewsDate } from "@/components/news-card";
import { type NewsFull, serverGet } from "@/lib/server-api";

async function load(slug: string): Promise<NewsFull | null> {
  return serverGet<NewsFull>(`/api/content/site/news/${encodeURIComponent(slug)}`);
}

export async function generateMetadata({ params }: PageProps<"/news/[slug]">): Promise<Metadata> {
  const n = await load((await params).slug);
  return n ? { title: `${n.title} — Тестматика`, description: n.summary || undefined } : { title: "Новость не найдена" };
}

/** Новость — Markdown, как материалы библиотеки. */
export default async function NewsItemPage({ params }: PageProps<"/news/[slug]">) {
  const n = await load((await params).slug);
  if (!n) notFound();
  return (
    <article className="mx-auto max-w-3xl space-y-5">
      <Link href="/news" className="text-sm text-fg-soft hover:text-fg">
        ← Все новости
      </Link>
      <p className="text-sm text-fg-soft">{fmtNewsDate(n.published_at)}</p>
      <h1 className="text-3xl font-semibold tracking-tight">{n.title}</h1>
      {n.summary && <p className="text-lg text-fg-soft">{n.summary}</p>}
      {n.cover_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={n.cover_url} alt="" className="w-full rounded-2xl border border-line object-cover" />
      )}
      <Markdown text={n.body} />
    </article>
  );
}
