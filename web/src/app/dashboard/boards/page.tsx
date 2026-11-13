"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { BoardThumbnail } from "@/components/whiteboard/board-thumbnail";
import { Pager } from "@/components/pager";
import { Alert, Badge, Button, EmptyState, Field, Modal, Select, Spinner } from "@/components/ui";
import { classroom, type BoardAccess, whiteboard } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

const PAGE = 24;
const ACCESS: Record<BoardAccess, string> = { none: "ученики не видят", read: "ученики смотрят", edit: "ученики рисуют" };

/** Все доски (решение №60): к занятиям и свободные. Ученик видит доски, которые педагог ему открыл. */
export default function BoardsPage() {
  const teacher = !!useAuth().user?.roles.includes("teacher");
  const [kind, setKind] = useState<"all" | "lesson" | "free">("all");
  const [page, setPage] = useState(0);
  const [creating, setCreating] = useState(false);
  const boards = useLoad(() => whiteboard.list({ kind, offset: page * PAGE, limit: PAGE + 1 }), [kind, page]);
  const shown = boards.data?.slice(0, PAGE) ?? [];
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Доски</h1>
        {teacher && <Button onClick={() => setCreating(true)}>Новая доска</Button>}
      </div>
      <div className="flex flex-wrap gap-2" role="tablist">
        {(
          [
            ["all", "Все"],
            ["lesson", "К занятиям"],
            ["free", "Свободные"],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            role="tab"
            aria-selected={kind === k}
            onClick={() => {
              setKind(k);
              setPage(0);
            }}
            className={`h-9 rounded-full border px-4 text-sm font-medium ${kind === k ? "border-brand bg-brand text-on-brand" : "border-line hover:bg-muted"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {boards.error && <Alert>{boards.error}</Alert>}
      {!boards.data ? (
        !boards.error && <Spinner />
      ) : !shown.length ? (
        <EmptyState
          title="Досок пока нет"
          text={
            teacher
              ? "Доску занятия откройте с карточки занятия в расписании, свободную — кнопкой «Новая доска»."
              : "Здесь появятся доски, которые педагог откроет вам."
          }
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((b) => (
            <li key={b.id}>
              <Link href={`/dashboard/boards/${b.id}`} className="block h-full overflow-hidden rounded-2xl border border-line bg-surface hover:border-brand">
                <BoardThumbnail board={b} />
                <div className="space-y-1.5 p-4">
                  <span className="line-clamp-2 font-medium">{b.title}</span>
                  <span className="block text-sm text-fg-soft">
                    {[b.lesson_id ? "к занятию" : "свободная", b.target_title, b.role === "owner" ? ACCESS[b.access] : b.owner_name]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                  <span className="flex items-center gap-2 text-xs text-fg-soft">
                    {b.role === "read" && <Badge>только просмотр</Badge>}
                    {b.role === "edit" && <Badge tone="ok">можно рисовать</Badge>}
                    изменена {fmtDate(b.updated_at, { day: "numeric", month: "short" })}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {boards.data && (
        <Pager
          page={page}
          hasNext={boards.data.length > PAGE}
          onPage={(p) => {
            setPage(p);
            window.scrollTo({ top: 0 });
          }}
        />
      )}
      {teacher && <NewBoard open={creating} onClose={() => setCreating(false)} />}
    </div>
  );
}

function NewBoard({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const targets = useLoad(async () => (open ? Promise.all([classroom.groups(), classroom.students()]) : null), [open]);
  const [title, setTitle] = useState("");
  const [target, setTarget] = useState("");
  const [access, setAccess] = useState<BoardAccess>("read");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  return (
    <Modal open={open} onClose={onClose} title="Новая доска">
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(undefined);
          const [kind, id] = target.split(":");
          try {
            const board = await whiteboard.create({
              title,
              group_id: kind === "group" ? id : null,
              student_id: kind === "student" ? id : null,
              access,
            });
            router.push(`/dashboard/boards/${board.id}`);
          } catch (err) {
            setError(errorText(err));
            setBusy(false);
          }
        }}
      >
        {error && <Alert>{error}</Alert>}
        <Field label="Название" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Разбор задач, черновик…" />
        <Select label="Кому видна" value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">Только мне</option>
          {targets.data && targets.data[0].length > 0 && (
            <optgroup label="Классы и группы">
              {targets.data[0].map((g) => (
                <option key={g.id} value={`group:${g.id}`}>
                  {g.title}
                </option>
              ))}
            </optgroup>
          )}
          {targets.data && targets.data[1].length > 0 && (
            <optgroup label="Ученики">
              {targets.data[1]
                .filter((s) => s.status === "active")
                .map((s) => (
                  <option key={s.student_id} value={`student:${s.student_id}`}>
                    {s.full_name}
                  </option>
                ))}
            </optgroup>
          )}
        </Select>
        {target && (
          <Select label="Ученики" value={access} onChange={(e) => setAccess(e.target.value as BoardAccess)}>
            <option value="read">Только смотрят</option>
            <option value="edit">Могут рисовать</option>
            <option value="none">Пока не видят</option>
          </Select>
        )}
        <Button type="submit" loading={busy} disabled={!title.trim()} className="w-full">
          Создать
        </Button>
      </form>
    </Modal>
  );
}
