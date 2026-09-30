/** Юридические документы сайта (решение №27): реквизиты оператора и редакции документов.
 *
 * Версия — дата редакции. Её же хранят сервисы вместе с согласием (identity — соглашение и ПД,
 * marketplace — распространение ПД в анкете, billing — оферта). Новая редакция: поменять дату здесь
 * и в сервисе — у всех, кто принимал прежнюю, снова появится окно согласия. */

export const OPERATOR = {
  name: "Самохвалов Вячеслав Дмитриевич",
  short: "Самохвалов В. Д.",
  status: "плательщик налога на профессиональный доход (самозанятый)",
  inn: "743003719146",
  email: "info@testmatica.ru",
};

/** Адрес сайта в документах — его же указывают в согласии на распространение ПД (приказ РКН № 18). */
export const SITE = { name: "ТестМатика", url: "https://testmatica.ru", host: "testmatica.ru" };

export type LegalSlug = "terms" | "privacy" | "consent" | "public-profile" | "offer";

export const LEGAL: Record<LegalSlug, { title: string; short: string; version: string }> = {
  terms: { title: "Пользовательское соглашение", short: "Пользовательское соглашение", version: "2026-09-30" },
  privacy: { title: "Политика обработки персональных данных", short: "Политика обработки ПД", version: "2026-09-30" },
  consent: { title: "Согласие на обработку персональных данных", short: "Согласие на обработку ПД", version: "2026-09-30" },
  "public-profile": {
    title: "Согласие на обработку персональных данных, разрешённых для распространения",
    short: "Согласие на распространение ПД (анкета репетитора)",
    version: "2026-09-30",
  },
  offer: { title: "Публичная оферта на тариф «Базовый»", short: "Оферта", version: "2026-09-30" },
};

export const LEGAL_ORDER: LegalSlug[] = ["terms", "privacy", "consent", "public-profile", "offer"];

export function legalHref(slug: LegalSlug): string {
  return `/legal/${slug}`;
}

/** «30 сентября 2026 г.» — дата редакции в шапке документа. */
export function fmtVersion(version: string): string {
  return new Date(`${version}T12:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
}
