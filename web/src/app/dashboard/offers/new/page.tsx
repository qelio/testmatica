"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { OfferForm } from "@/components/offers";

export default function NewOfferPage() {
  const router = useRouter();
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Link href="/dashboard/offers" className="text-sm text-fg-soft hover:text-fg">
        ← Наборы в группы
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">Новый набор в группу</h1>
      <div className="rounded-2xl border border-line bg-surface p-5">
        <OfferForm onSaved={(o) => router.replace(`/dashboard/offers/${o.id}`)} />
      </div>
    </div>
  );
}
