"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Button } from "@/components/ui";
import { admin, type AuditRecord } from "@/lib/api";
import { eventLabel } from "@/lib/admin";
import { fmtDateTime } from "@/lib/dates";
import { useLoad } from "@/lib/hooks";

/** История: действия пользователя и действия, которые касались его (журнал аудита). */
export function History({ userId }: { userId: string }) {
  const [items, setItems] = useState<AuditRecord[]>([]);
  const [done, setDone] = useState(false);
  const first = useLoad(() => admin.audit({ user_id: userId, limit: 30 }), [userId]);
  const all = [...(first.data ?? []), ...items];
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold">История действий</h2>
      {first.error && <Alert>{first.error}</Alert>}
      <AuditList records={all} />
      {first.data && first.data.length === 30 && !done && (
        <Button
          variant="secondary"
          onClick={async () => {
            const more = await admin.audit({ user_id: userId, limit: 30, before: all[all.length - 1].occurred_at });
            setItems([...items, ...more]);
            if (more.length < 30) setDone(true);
          }}
        >
          Показать ещё
        </Button>
      )}
    </section>
  );
}

export function AuditList({ records, names }: { records: AuditRecord[]; names?: Record<string, string> }) {
  if (!records.length) return <p className="text-sm text-fg-soft">Событий нет.</p>;
  return (
    <ul className="divide-y divide-line rounded-2xl border border-line bg-surface text-sm">
      {records.map((r) => (
        <li key={r.event_id} className="px-4 py-2">
          <details>
            <summary className="flex cursor-pointer flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-fg-soft tabular-nums">{fmtDateTime(r.occurred_at)}</span>
              <span className="font-medium">{eventLabel(r.type)}</span>
              {names && r.actor_id && (
                <Link href={`/dashboard/users/${r.actor_id}`} className="text-brand-text hover:underline">
                  {names[r.actor_id] ?? "пользователь"}
                </Link>
              )}
              <span className="text-xs text-fg-soft">{r.type}</span>
            </summary>
            <pre className="mt-2 overflow-x-auto rounded-lg bg-muted p-3 text-xs">{JSON.stringify(r.data, null, 2)}</pre>
          </details>
        </li>
      ))}
    </ul>
  );
}
