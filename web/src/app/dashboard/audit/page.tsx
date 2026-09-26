"use client";

import { useEffect, useState } from "react";

import { AuditList } from "@/components/audit-list";
import { Alert, Button, Select, Spinner } from "@/components/ui";
import { admin, type AuditRecord } from "@/lib/api";
import { AUDIT_PREFIXES } from "@/lib/admin";
import { errorText } from "@/lib/hooks";

const PAGE = 50;

/** Журнал аудита: все события платформы, неизменяемый (ТЗ: «история действий»). */
export default function AuditPage() {
  const [prefix, setPrefix] = useState("");
  const [records, setRecords] = useState<AuditRecord[] | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [more, setMore] = useState(true);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function load(reset: boolean) {
    setBusy(true);
    setError(undefined);
    try {
      const before = reset || !records?.length ? undefined : records[records.length - 1].occurred_at;
      const page = await admin.audit({ type_prefix: prefix || undefined, before, limit: PAGE });
      const all = reset ? page : [...(records ?? []), ...page];
      setRecords(all);
      setMore(page.length === PAGE);
      // Имена тех, кто действовал.
      const unknown = [...new Set(page.map((r) => r.actor_id).filter((a): a is string => !!a && !(a in names)))];
      if (unknown.length) {
        const users = await admin.users({ ids: unknown, limit: 200 });
        setNames((n) => ({ ...n, ...Object.fromEntries(users.items.map((u) => [u.id, u.full_name])) }));
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    // Новая выборка при смене фильтра.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix]);

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Журнал аудита</h1>
        <p className="mt-1 text-sm text-fg-soft">Все события платформы. Журнал только дополняется — изменить или удалить записи нельзя.</p>
      </div>
      <div className="max-w-xs">
        <Select label="Раздел" value={prefix} onChange={(e) => setPrefix(e.target.value)}>
          {AUDIT_PREFIXES.map(([value, title]) => (
            <option key={value} value={value}>
              {title}
            </option>
          ))}
        </Select>
      </div>
      {error && <Alert>{error}</Alert>}
      {records === null ? <Spinner /> : <AuditList records={records} names={names} />}
      {records && more && (
        <Button variant="secondary" loading={busy} onClick={() => load(false)}>
          Показать ещё
        </Button>
      )}
    </div>
  );
}
