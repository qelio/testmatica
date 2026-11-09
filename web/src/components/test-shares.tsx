"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button } from "@/components/ui";
import { assessment, colleagues, type Quiz } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorText, useLoad } from "@/lib/hooks";

/** Поделиться тестом с коллегами (решение №58): автор и те, с кем уже поделились. Коллега тест не меняет. */
export function TestShares({ test }: { test: Quiz }) {
  const router = useRouter();
  const me = useAuth().user?.id;
  const shares = useLoad(() => assessment.testShares(test.id), [test.id]);
  const list = useLoad(() => colleagues.list(), []);
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sharedIds = new Set((shares.data ?? []).map((s) => s.user_id));
  const options = (list.data?.colleagues ?? []).filter((c) => !sharedIds.has(c.user_id) && c.user_id !== me);
  const mine = (shares.data ?? []).find((s) => s.user_id === me);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setPick("");
      shares.reload();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function leave() {
    if (!me || !window.confirm("Убрать тест из ваших? Ваши назначения по нему останутся.")) return;
    setBusy(true);
    try {
      await assessment.unshareTest(test.id, me);
      router.push("/dashboard/tests");
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  const others = (shares.data ?? []).filter((s) => s.user_id !== me);
  return (
    <section className="space-y-3 rounded-2xl border border-line bg-surface px-5 py-4">
      <h2 className="font-medium">Коллеги с доступом к тесту</h2>
      <p className="text-sm text-fg-soft">
        Коллега видит тест и его задачи, назначает его своим ученикам и классам и может поделиться им дальше. Менять тест он не может, а
        личные задачи теста в общий банк не попадают.
      </p>
      {error && <Alert>{error}</Alert>}
      {others.length > 0 && (
        <ul className="divide-y divide-line rounded-xl border border-line">
          {others.map((s) => (
            <li key={s.user_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-sm">
              <span className="min-w-0 flex-1">
                <span className="font-medium">{s.full_name}</span>
                {s.shared_by !== me && <span className="text-fg-soft"> · доступ от: {s.shared_by_name}</span>}
              </span>
              {s.can_remove && (
                <Button
                  variant="ghost"
                  className="h-9 text-danger"
                  disabled={busy}
                  onClick={() =>
                    window.confirm(`Закрыть доступ коллеге ${s.full_name}? Его назначения по тесту останутся.`) &&
                    run(() => assessment.unshareTest(test.id, s.user_id))
                  }
                >
                  Закрыть доступ
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {list.data && !list.data.colleagues.length ? (
        <p className="text-sm">
          Коллег пока нет —{" "}
          <Link href="/dashboard/colleagues" className="text-brand-text hover:underline">
            добавьте их в «Мои коллеги»
          </Link>
          .
        </p>
      ) : (
        options.length > 0 && (
          <div className="flex flex-wrap gap-2">
            <select
              value={pick}
              onChange={(e) => setPick(e.target.value)}
              aria-label="Коллега"
              className="h-10 min-w-0 flex-1 rounded-xl border border-line bg-surface px-3 text-sm"
            >
              <option value="">Выберите коллегу</option>
              {options.map((c) => (
                <option key={c.user_id} value={c.user_id}>
                  {c.full_name}
                </option>
              ))}
            </select>
            <Button className="h-10" loading={busy} disabled={!pick} onClick={() => run(() => assessment.shareTest(test.id, pick))}>
              Поделиться
            </Button>
          </div>
        )
      )}
      {mine && (
        <Button variant="ghost" className="h-9 text-danger" disabled={busy} onClick={leave}>
          Убрать тест из моих
        </Button>
      )}
    </section>
  );
}
