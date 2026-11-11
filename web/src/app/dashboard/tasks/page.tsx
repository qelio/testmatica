"use client";

import Link from "next/link";
import { useState } from "react";

import { ExamItemSelect } from "@/components/exams";
import { Pager } from "@/components/pager";
import { TaskBankCard } from "@/components/task-bank-card";
import { buildRubric, topicFilter, TopicTree } from "@/components/topics";
import { Alert, EmptyState, Select, Spinner } from "@/components/ui";
import { assessment, type TaskType } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { TASK_TYPE_LABELS } from "@/lib/format";
import { useLoad } from "@/lib/hooks";

type Scope = "mine" | "public";

const PAGE = 20;

/** Банк задач: рубрикатор «предмет → раздел → тема» слева, задачи выбранного узла справа — с условиями, по 20. */
export default function TaskBankPage() {
  const { user } = useAuth();
  const staff = !!user?.roles.some((r) => r === "moderator" || r === "admin");
  const [scope, setScope] = useState<Scope>("mine");
  const [node, setNode] = useState("");
  const [treeOpen, setTreeOpen] = useState(false);
  const [filters, setFilters] = useState({ type: "", difficulty: "", exam_item_id: "" });
  const exams = useLoad(() => assessment.exams(), []);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");

  const topics = useLoad(() => assessment.topics(scope), [scope]);
  const counts = useLoad(
    async () => {
      const [all, none] = await Promise.all([
        assessment.search({ scope, limit: 1 }),
        assessment.search({ scope, no_topic: true, limit: 1 }),
      ]);
      return { all: all.total, none: none.total };
    },
    [scope],
  );
  // По 20 задач на страницу, с полными условиями; смена фильтров — снова первая страница.
  const filterKey = JSON.stringify([scope, search, filters, node]);
  const [pageState, setPageState] = useState({ key: filterKey, n: 0 });
  const page = pageState.key === filterKey ? pageState.n : 0;
  const tasks = useLoad(
    () => assessment.search({ scope, q: search, ...filters, ...topicFilter(node), limit: PAGE, offset: page * PAGE, full: true }),
    [scope, search, filters, node, page],
  );
  const rubric = buildRubric(topics.data ?? []);
  const set = (k: keyof typeof filters, v: string) => setFilters((f) => ({ ...f, [k]: v }));
  const nodeTitle = nodeName(rubric, node);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Банк задач</h1>
        <div className="flex gap-2">
          {staff && (
            <Link href="/dashboard/tasks/exams" className="rounded-xl border border-line px-4 py-2.5 text-sm font-medium hover:bg-muted">
              ЕГЭ и ОГЭ
            </Link>
          )}
          {staff && (
            <Link href="/dashboard/tasks/topics" className="rounded-xl border border-line px-4 py-2.5 text-sm font-medium hover:bg-muted">
              Рубрикатор
            </Link>
          )}
          <Link href="/dashboard/tasks/new" className="rounded-xl bg-brand px-4 py-2.5 text-sm font-medium text-on-brand hover:bg-brand-strong">
            Новая задача
          </Link>
        </div>
      </div>
      <div className="flex rounded-xl border border-line bg-muted p-1 text-sm sm:w-fit" role="tablist">
        {(["mine", "public"] as const).map((s) => (
          <button
            key={s}
            role="tab"
            aria-selected={scope === s}
            onClick={() => {
              setScope(s);
              setNode("");
            }}
            className={`flex-1 rounded-lg px-4 py-1.5 font-medium whitespace-nowrap ${scope === s ? "bg-surface shadow-sm" : "text-fg-soft hover:text-fg"}`}
          >
            {s === "mine" ? "Мои задачи" : "Публичный банк"}
          </button>
        ))}
      </div>

      <div className="gap-5 lg:grid lg:grid-cols-[18rem_1fr]">
        <aside className="mb-4 lg:mb-0">
          <button
            onClick={() => setTreeOpen((o) => !o)}
            aria-expanded={treeOpen}
            className="flex w-full items-center justify-between rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-medium lg:hidden"
          >
            <span className="truncate">Разделы: {nodeTitle}</span>
            <span className="text-fg-soft">{treeOpen ? "▲" : "▼"}</span>
          </button>
          <div className={`${treeOpen ? "mt-2 block" : "hidden"} max-h-[70vh] overflow-y-auto rounded-2xl border border-line bg-surface p-2 lg:sticky lg:top-4 lg:mt-0 lg:block lg:max-h-[calc(100vh-8rem)]`}>
            {!topics.data ? (
              <Spinner />
            ) : (
              <TopicTree
                key={scope}
                rubric={rubric}
                selected={node}
                onSelect={(k) => {
                  setNode(k);
                  if (!k.startsWith("subject:")) setTreeOpen(false);
                }}
                total={counts.data?.all ?? 0}
                noTopic={counts.data?.none ?? 0}
              />
            )}
          </div>
        </aside>

        <section className="min-w-0 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <form
              className="sm:col-span-2 xl:col-span-2"
              onSubmit={(e) => {
                e.preventDefault();
                setSearch(q.trim());
              }}
            >
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium">Поиск</span>
                <input
                  type="search"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Название или текст условия"
                  className="h-11 w-full rounded-xl border border-line bg-surface px-3.5 outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
                />
              </label>
            </form>
            <Select label="Тип" value={filters.type} onChange={(e) => set("type", e.target.value)}>
              <option value="">Все</option>
              {(Object.keys(TASK_TYPE_LABELS) as TaskType[]).map((t) => (
                <option key={t} value={t}>
                  {TASK_TYPE_LABELS[t]}
                </option>
              ))}
            </Select>
            <Select label="Сложность" value={filters.difficulty} onChange={(e) => set("difficulty", e.target.value)}>
              <option value="">Любая</option>
              <option value="1">Базовая</option>
              <option value="2">Средняя</option>
              <option value="3">Сложная</option>
            </Select>
            <ExamItemSelect
              exams={exams.data ?? []}
              value={filters.exam_item_id}
              onChange={(v) => set("exam_item_id", v)}
              label="ЕГЭ / ОГЭ"
              empty="Любое задание"
            />
          </div>

          {tasks.error && <Alert>{tasks.error}</Alert>}
          {!tasks.data ? (
            <Spinner />
          ) : tasks.data.items.length === 0 ? (
            <EmptyState
              title={node ? "В этом разделе пока нет задач" : scope === "mine" ? "У вас пока нет задач" : "Ничего не найдено"}
              text={
                scope === "mine"
                  ? "Создайте задачу или возьмите за основу задачу из публичного банка."
                  : "Выберите другой раздел или измените фильтры."
              }
            />
          ) : (
            <>
              <p className="text-sm text-fg-soft">
                {nodeTitle} · найдено: {tasks.data.total}
              </p>
              <ul className="space-y-3">
                {(tasks.data.details ?? []).map((t) => (
                  <li key={t.id}>
                    <TaskBankCard task={t} scope={scope} />
                  </li>
                ))}
              </ul>
              <Pager
                page={page}
                hasNext={(page + 1) * PAGE < tasks.data.total}
                onPage={(n) => {
                  setPageState({ key: filterKey, n });
                  window.scrollTo({ top: 0 });
                }}
              />
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function nodeName(rubric: ReturnType<typeof buildRubric>, key: string): string {
  if (!key) return "Все задачи";
  if (key === "none") return "Без темы";
  for (const s of rubric) {
    if (key === `subject:${s.id}`) return s.name;
    for (const sec of s.sections) {
      if (sec.id === key) return `${s.name} › ${sec.title}`;
      const t = sec.children.find((c) => c.id === key);
      if (t) return `${sec.title} › ${t.title}`;
    }
  }
  return "Раздел";
}
