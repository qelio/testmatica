import Link from "next/link";
import { notFound } from "next/navigation";

import { Markdown } from "@/components/markdown";
import { fmtVersion, LEGAL, LEGAL_ORDER, type LegalSlug } from "@/lib/legal";
import { LEGAL_TEXTS } from "@/lib/legal-docs";

function doc(slug: string) {
  return slug in LEGAL ? { slug: slug as LegalSlug, ...LEGAL[slug as LegalSlug] } : null;
}

export function generateStaticParams() {
  return LEGAL_ORDER.map((slug) => ({ slug }));
}

export default async function LegalDocPage({ params }: PageProps<"/legal/[slug]">) {
  const d = doc((await params).slug);
  if (!d) notFound();
  return (
    <article className="mx-auto max-w-3xl space-y-4">
      <Link href="/legal" className="text-sm text-fg-soft hover:text-fg">
        ← Все документы
      </Link>
      <h1 className="text-3xl font-semibold tracking-tight text-balance">{d.title}</h1>
      <p className="text-sm text-fg-soft">Редакция от {fmtVersion(d.version)}</p>
      <div className="rounded-2xl border border-line bg-surface p-5 sm:p-8">
        <Markdown text={LEGAL_TEXTS[d.slug]} />
      </div>
    </article>
  );
}
