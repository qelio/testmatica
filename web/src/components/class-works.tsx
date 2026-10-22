"use client";

import { useState } from "react";

import { AssignmentCard } from "@/components/assignment-card";
import { Pager } from "@/components/pager";
import { Alert, Spinner } from "@/components/ui";
import { assessment } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

const PAGE = 10;

/** «Работы класса» (решение №61): все работы, выданные классу его педагогами, — у класса с коллегами,
 * владельцу и коллегам с правом «Работы класса». */
export function ClassWorks({ groupId }: { groupId: string }) {
  const [page, setPage] = useState(0);
  const list = useLoad(
    () => assessment.assignments("teacher", { scope: "class", target_id: groupId, offset: page * PAGE, limit: PAGE + 1 }),
    [groupId, page],
  );
  const shown = list.data?.slice(0, PAGE) ?? [];
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Работы класса</h2>
      <p className="text-sm text-fg-soft">Работы, которые классу назначили все его педагоги: ход, проверка и результаты.</p>
      {list.error ? (
        <Alert>{list.error}</Alert>
      ) : !list.data ? (
        <Spinner />
      ) : !shown.length ? (
        <p className="rounded-2xl border border-line bg-surface px-5 py-4 text-sm text-fg-soft">Классу пока не назначали работ.</p>
      ) : (
        <>
          <ul className="space-y-2">
            {shown.map((a) => (
              <li key={a.id}>
                <AssignmentCard a={a} inClass />
              </li>
            ))}
          </ul>
          <Pager page={page} hasNext={list.data.length > PAGE} onPage={setPage} />
        </>
      )}
    </section>
  );
}
