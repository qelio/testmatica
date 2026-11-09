"use client";

import { useState } from "react";

import { Select } from "@/components/ui";
import type { Topic } from "@/lib/api";

export type TopicNode = Topic & { children: TopicNode[]; total: number };
export type SubjectNode = { id: string; name: string; sections: TopicNode[]; total: number };

/** Плоский список тем → предметы → разделы → темы; total — задач вместе с вложенными темами. */
export function buildRubric(topics: Topic[]): SubjectNode[] {
  const byPos = (a: Topic, b: Topic) => a.position - b.position || a.title.localeCompare(b.title, "ru");
  const subjects = new Map<string, SubjectNode>();
  const sections = topics.filter((t) => !t.parent_id).sort(byPos);
  for (const s of sections) {
    const children = topics
      .filter((t) => t.parent_id === s.id)
      .sort(byPos)
      .map((t) => ({ ...t, children: [], total: t.count }));
    const node: TopicNode = { ...s, children, total: s.count + children.reduce((n, c) => n + c.total, 0) };
    const subject = subjects.get(s.subject_id) ?? { id: s.subject_id, name: s.subject_name, sections: [], total: 0 };
    subject.sections.push(node);
    subject.total += node.total;
    subjects.set(s.subject_id, subject);
  }
  return [...subjects.values()].sort((a, b) => a.name.localeCompare(b.name, "ru"));
}

/** Выбор в дереве: "" — все задачи, "none" — без темы, "subject:<id>" — предмет, иначе id раздела или темы. */
export function topicFilter(key: string): Record<string, string | boolean | undefined> {
  if (!key) return {};
  if (key === "none") return { no_topic: true };
  if (key.startsWith("subject:")) return { subject_id: key.slice(8) };
  return { topic_id: key };
}

function Count({ n }: { n: number }) {
  return <span className={`ml-auto shrink-0 text-xs tabular-nums ${n ? "text-fg-soft" : "text-fg-soft/50"}`}>{n}</span>;
}

function Caret({ open }: { open: boolean }) {
  return <span className={`inline-block w-3 shrink-0 text-[10px] text-fg-soft transition-transform ${open ? "rotate-90" : ""}`}>▶</span>;
}

/** Дерево рубрикатора с числом задач в каждом узле. */
export function TopicTree({
  rubric,
  selected,
  onSelect,
  total,
  noTopic,
}: {
  rubric: SubjectNode[];
  selected: string;
  onSelect: (key: string) => void;
  total: number;
  noTopic: number;
}) {
  // Раскрыт путь к выбранному узлу; остальное — по клику.
  const [open, setOpen] = useState<Set<string>>(() => {
    const keys = new Set<string>();
    for (const s of rubric)
      for (const sec of s.sections)
        if (selected === sec.id || sec.children.some((c) => c.id === selected)) keys.add(s.id).add(sec.id);
    return keys;
  });
  const toggle = (id: string) =>
    setOpen((o) => {
      const next = new Set(o);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const row = (active: boolean) =>
    `flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-sm ${active ? "bg-brand/10 font-medium text-brand-text" : "hover:bg-muted"}`;

  return (
    <nav aria-label="Рубрикатор" className="space-y-0.5">
      <button onClick={() => onSelect("")} className={row(selected === "")} aria-current={selected === "" || undefined}>
        Все задачи
        <Count n={total} />
      </button>
      {rubric.map((s) => (
        <div key={s.id}>
          <button
            onClick={() => {
              toggle(s.id);
              onSelect(`subject:${s.id}`);
            }}
            aria-expanded={open.has(s.id)}
            className={row(selected === `subject:${s.id}`)}
          >
            <Caret open={open.has(s.id)} />
            <span className="min-w-0 truncate">{s.name}</span>
            <Count n={s.total} />
          </button>
          {open.has(s.id) && (
            <ul className="ml-3 border-l border-line pl-1.5">
              {s.sections.map((sec) => (
                <li key={sec.id}>
                  <button
                    onClick={() => {
                      if (sec.children.length) toggle(sec.id);
                      onSelect(sec.id);
                    }}
                    aria-expanded={sec.children.length ? open.has(sec.id) : undefined}
                    className={row(selected === sec.id)}
                  >
                    {sec.children.length > 0 ? <Caret open={open.has(sec.id)} /> : <span className="w-3" />}
                    <span className="min-w-0 truncate">{sec.title}</span>
                    <Count n={sec.total} />
                  </button>
                  {open.has(sec.id) && (
                    <ul className="ml-3 border-l border-line pl-1.5">
                      {sec.children.map((t) => (
                        <li key={t.id}>
                          <button onClick={() => onSelect(t.id)} className={row(selected === t.id)}>
                            <span className="min-w-0 truncate">{t.title}</span>
                            <Count n={t.total} />
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
      {noTopic > 0 && (
        <button onClick={() => onSelect("none")} className={row(selected === "none")}>
          <span className="italic">Без темы</span>
          <Count n={noTopic} />
        </button>
      )}
    </nav>
  );
}

/** Выбор темы для задачи: предметы — группами, внутри — разделы и их темы. */
export function TopicSelect({
  rubric,
  value,
  onChange,
  label = "Тема",
  empty = "Не выбрана",
}: {
  rubric: SubjectNode[];
  value: string;
  onChange: (id: string) => void;
  label?: string;
  empty?: string;
}) {
  return (
    <Select label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{empty}</option>
      {rubric.map((s) => (
        <optgroup key={s.id} label={s.name}>
          {s.sections.flatMap((sec) => [
            <option key={sec.id} value={sec.id}>
              {sec.title}
            </option>,
            ...sec.children.map((t) => (
              <option key={t.id} value={t.id}>
                {"   — "}
                {t.title}
              </option>
            )),
          ])}
        </optgroup>
      ))}
    </Select>
  );
}

/** «Раздел › Тема» для карточек задач. */
export function topicLabel(path: string[], subject?: string | null): string {
  return [subject, ...path].filter(Boolean).join(" › ");
}
