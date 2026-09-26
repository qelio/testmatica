"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { Alert, Spinner } from "@/components/ui";
import { marketplace } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

/** Документ об образовании для модератора: решение принимается в очереди модерации. */
export default function EducationReviewPage() {
  const { id } = useParams<{ id: string }>();
  const doc = useLoad(() => marketplace.educationForModerator(id), [id]);
  if (doc.error) return <Alert>{doc.error}</Alert>;
  if (!doc.data) return <Spinner />;
  const d = doc.data;
  const pdf = d.filename?.toLowerCase().endsWith(".pdf");
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <Link href="/dashboard/moderation" className="text-sm text-fg-soft hover:text-fg">
        ← Очередь модерации
      </Link>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{d.title}</h1>
        <p className="mt-1 text-fg-soft">
          {d.institution}, {d.year} · {d.filename}
        </p>
      </div>
      <p className="text-sm text-fg-soft">Проверьте, что документ читается и совпадает с описанием. Одобрить или отклонить с комментарием — в очереди.</p>
      {!d.file_url ? (
        <Alert>Файл недоступен.</Alert>
      ) : pdf ? (
        <iframe src={d.file_url} title={d.title} className="h-[75vh] w-full rounded-xl border border-line" />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element -- временная ссылка S3
        <img src={d.file_url} alt={d.title} className="max-h-[75vh] max-w-full rounded-xl border border-line" />
      )}
    </div>
  );
}
