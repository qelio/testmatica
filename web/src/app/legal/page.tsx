import type { Metadata } from "next";
import Link from "next/link";

import { fmtVersion, LEGAL, LEGAL_ORDER, legalHref, OPERATOR } from "@/lib/legal";

export const metadata: Metadata = { title: "Документы — ТестМатика" };

export default function LegalIndexPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Документы</h1>
      <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
        {LEGAL_ORDER.map((slug) => (
          <li key={slug}>
            <Link href={legalHref(slug)} className="block px-5 py-4 hover:bg-muted/60">
              <span className="font-medium">{LEGAL[slug].title}</span>
              <span className="block text-sm text-fg-soft">Редакция от {fmtVersion(LEGAL[slug].version)}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="text-sm text-fg-soft">
        {OPERATOR.name}, {OPERATOR.status}, ИНН {OPERATOR.inn}. Вопросы — на{" "}
        <a href={`mailto:${OPERATOR.email}`} className="text-brand hover:underline">
          {OPERATOR.email}
        </a>
        .
      </p>
    </div>
  );
}
