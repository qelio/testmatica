// Запросы к API с сервера Next (главная, новости): рендер на сервере — страницы видят поисковики.
// Внутри Docker сервер ходит в шлюз по внутреннему адресу; в браузере тот же API — по относительным путям.

import type { TutorCard } from "@/lib/api";

const ORIGIN = process.env.INTERNAL_API_ORIGIN ?? "http://traefik";

/** GET публичного API; кэш на revalidate секунд. null — не найдено или сервис недоступен (страница покажет заглушку). */
export async function serverGet<T>(path: string, revalidate = 30): Promise<T | null> {
  try {
    const resp = await fetch(`${ORIGIN}${path}`, { next: { revalidate } });
    if (!resp.ok) return null;
    return (await resp.json()) as T;
  } catch {
    return null;
  }
}

export type LandingIcon =
  | "book"
  | "users"
  | "calendar"
  | "video"
  | "chart"
  | "shield"
  | "sparkles"
  | "graduation"
  | "target"
  | "message"
  | "wallet"
  | "check";

export type NewsSummary = {
  id: string;
  slug: string;
  title: string;
  summary: string;
  cover_url: string | null;
  status: "draft" | "published";
  published_at: string | null;
  updated_at: string;
};
export type NewsFull = NewsSummary & { body: string; cover_file_id: string | null };

export type Landing = {
  hero: {
    title: string;
    subtitle: string;
    primary_text: string;
    primary_href: string;
    secondary_text: string;
    secondary_href: string;
    image_file_id: string | null;
  };
  stats: { value: string; label: string }[];
  features: { icon: LandingIcon; title: string; text: string }[];
  steps: { title: string; students: string[]; teachers: string[] };
  teachers: { title: string; subtitle: string; items: { user_id: string; note: string }[] };
  news: { title: string; count: number };
  faq: { q: string; a: string }[];
  contacts: { text: string; email: string; phone: string; telegram: string; vk: string; address: string };
  sections: { stats: boolean; features: boolean; steps: boolean; teachers: boolean; news: boolean; faq: boolean };
};
export type LandingOut = Landing & { hero_image_url: string | null; latest_news: NewsSummary[]; updated_at: string | null };

/** Карточки выбранных преподавателей в заданном администратором порядке (скрытые профили не попадут). */
export async function featuredTutors(ids: string[]): Promise<TutorCard[]> {
  if (!ids.length) return [];
  const qs = new URLSearchParams(ids.map((id) => ["ids", id]));
  const found = await serverGet<{ items: TutorCard[] }>(`/api/marketplace/tutors?${qs}&limit=50`);
  const byId = new Map((found?.items ?? []).map((t) => [t.user_id, t]));
  return ids.map((id) => byId.get(id)).filter((t): t is TutorCard => !!t);
}
