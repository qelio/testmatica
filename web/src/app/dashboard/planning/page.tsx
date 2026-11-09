"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { STATUS_LABELS } from "@/components/course-view";
import { Alert, Badge, EmptyState, Spinner } from "@/components/ui";
import { planning } from "@/lib/api";
import { fmtDate } from "@/lib/dates";
import { useLoad } from "@/lib/hooks";

export default function PlanningPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Planning />
    </Suspense>
  );
}

function Planning() {
  const router = useRouter();
  const tab = useSearchParams().get("tab") === "templates" ? "templates" : "plans";
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Планирование (КТП)</h1>
          <p className="mt-1 text-sm text-fg-soft">Необязательный инструмент: можно работать и без него, указывая тему каждого урока вручную.</p>
        </div>
        <Link
          href={tab === "plans" ? "/dashboard/planning/new" : "/dashboard/planning/templates/new"}
          className="rounded-xl bg-brand px-4 py-2.5 text-sm font-medium text-on-brand hover:bg-brand-strong"
        >
          {tab === "plans" ? "Новый КТП" : "Новый шаблон"}
        </Link>
      </div>
      <div className="flex rounded-xl border border-line bg-muted p-1 text-sm sm:w-fit" role="tablist">
        {(
          [
            ["plans", "КТП классов и учеников"],
            ["templates", "Шаблоны"],
          ] as const
        ).map(([key, title]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => router.replace(key === "templates" ? "/dashboard/planning?tab=templates" : "/dashboard/planning")}
            className={`flex-1 rounded-lg px-4 py-1.5 font-medium whitespace-nowrap ${tab === key ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`}
          >
            {title}
          </button>
        ))}
      </div>
      {tab === "plans" ? <Plans /> : <Templates />}
    </div>
  );
}

function Plans() {
  const plans = useLoad(() => planning.plans(), []);
  if (plans.error) return <Alert>{plans.error}</Alert>;
  if (!plans.data) return <Spinner />;
  if (!plans.data.length)
    return (
      <EmptyState
        title="КТП пока нет"
        text="Создайте план для класса, группы или ученика: с нуля, постепенно по мере уроков или на основе шаблона — даты проставятся по расписанию."
      />
    );
  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {plans.data.map((p) => (
        <li key={p.id}>
          <Link href={`/dashboard/planning/${p.id}`} className="block h-full rounded-2xl border border-line bg-surface p-5 hover:border-brand/50">
            <p className="font-medium">{p.title}</p>
            <p className="mt-0.5 text-sm text-fg-soft">{[p.target_title, p.subject].filter(Boolean).join(" · ")}</p>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
              <div className="h-full bg-ok" style={{ width: `${p.lessons_count ? (p.done_count / p.lessons_count) * 100 : 0}%` }} />
            </div>
            <p className="mt-1.5 text-sm text-fg-soft">
              Пройдено {p.done_count} из {p.lessons_count}
              {p.next_topic && (
                <>
                  {" · дальше: "}
                  <span className="text-fg">{p.next_topic}</span>
                  {p.next_date && ` (${fmtDate(p.next_date)})`}
                </>
              )}
            </p>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Templates() {
  const [scope, setScope] = useState<"mine" | "public">("mine");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const list = useLoad(() => planning.templates(scope, search), [scope, search]);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex rounded-lg bg-muted p-0.5 text-sm">
          {(["mine", "public"] as const).map((s) => (
            <button
              key={s}
              aria-pressed={scope === s}
              onClick={() => setScope(s)}
              className={`rounded-md px-3 py-1 font-medium ${scope === s ? "bg-surface shadow-sm" : "text-fg-soft"}`}
            >
              {s === "mine" ? "Мои" : "Библиотека"}
            </button>
          ))}
        </div>
        <form
          className="min-w-0 flex-1"
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(q.trim());
          }}
        >
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Поиск по названию или классу"
            aria-label="Поиск шаблонов"
            className="h-10 w-full rounded-xl border border-line bg-surface px-3.5 text-sm outline-none focus:border-brand"
          />
        </form>
      </div>
      {list.error && <Alert>{list.error}</Alert>}
      {!list.data ? (
        !list.error && <Spinner />
      ) : !list.data.length ? (
        <EmptyState
          title={scope === "mine" ? "Своих шаблонов пока нет" : "Ничего не найдено"}
          text={scope === "mine" ? "Шаблон — список уроков без дат. Его можно привязать к нескольким классам, у каждого — свои даты." : undefined}
        />
      ) : (
        <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
          {list.data.map((t) => (
            <li key={t.id}>
              <Link href={`/dashboard/planning/templates/${t.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-3 hover:bg-muted">
                <span className="min-w-0 flex-1 font-medium">{t.title}</span>
                {scope === "mine" && t.status !== "private" && <Badge tone={STATUS_LABELS[t.status].tone}>{STATUS_LABELS[t.status].text}</Badge>}
                <span className="w-full text-sm text-fg-soft sm:w-auto">
                  {[t.subject, t.level, `уроков: ${t.lessons_count}`, scope === "public" ? t.author_name : null].filter(Boolean).join(" · ")}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
