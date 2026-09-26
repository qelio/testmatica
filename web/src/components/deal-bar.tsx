"use client";

import { useState } from "react";

import { Alert, Badge, Button } from "@/components/ui";
import { marketplace } from "@/lib/api";
import { fmtRub, fmtSchedule, GOAL_LABELS } from "@/lib/format";
import { errorText, useLoad } from "@/lib/hooks";
import { useRealtime } from "@/lib/realtime";

/** Панель переговоров в чате заявки: цена, «Предложить цену», «Договорились», «Отказаться». */
export function DealBar({ responseId }: { responseId: string }) {
  const deal = useLoad(() => marketplace.negotiation(responseId), [responseId]);
  const [price, setPrice] = useState("");
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  useRealtime((e) => {
    if (e.type === "refresh" && e.conversation_id === responseId) deal.reload();
  });

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
      deal.reload();
      setEditing(false);
      setPrice("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (!deal.data) return deal.error ? <div className="border-b border-line px-4 py-2 text-sm text-fg-soft">{deal.error}</div> : null;
  const { response: r, request: q, role, can_agree } = deal.data;
  const active = r.status === "active" && q.status === "open";
  const byMe = r.proposed_by === role;

  return (
    <div className="space-y-2 border-b border-line bg-muted/60 px-4 py-3 text-sm">
      <p className="text-fg-soft">
        {q.subject_name} · {GOAL_LABELS[q.goal]} · {q.duration_min} мин · {fmtSchedule(q.schedule)}
        {q.comment && <span className="block truncate">«{q.comment}»</span>}
      </p>
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-base font-semibold">{fmtRub(r.price)}</span>
        <span className="text-fg-soft">
          за занятие · {r.status === "agreed" ? "договорились" : byMe ? "ваше предложение" : role === "student" ? "предлагает репетитор" : "предлагает ученик"}
        </span>
        {r.status === "agreed" && <Badge tone="ok">договорились</Badge>}
        {r.status === "closed" && <Badge>переговоры завершены</Badge>}
        {active && (
          <span className="ml-auto flex flex-wrap items-center gap-2">
            {editing ? (
              <form
                className="flex items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (Number(price) >= 100) void act(() => marketplace.proposePrice(responseId, Number(price)));
                }}
              >
                <input
                  type="number"
                  min={100}
                  step={50}
                  autoFocus
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  placeholder="Цена, ₽"
                  aria-label="Своя цена"
                  className="h-9 w-28 rounded-lg border border-line bg-surface px-2.5"
                />
                <Button type="submit" className="h-9" loading={busy}>
                  Предложить
                </Button>
                <Button type="button" variant="ghost" className="h-9" onClick={() => setEditing(false)}>
                  Отмена
                </Button>
              </form>
            ) : (
              <>
                {can_agree && (
                  <Button className="h-9" loading={busy} onClick={() => act(() => marketplace.agree(responseId))}>
                    Договорились
                  </Button>
                )}
                <Button variant="secondary" className="h-9" onClick={() => setEditing(true)}>
                  {byMe ? "Изменить цену" : "Предложить свою цену"}
                </Button>
                <Button
                  variant="ghost"
                  className="h-9 text-fg-soft"
                  onClick={() =>
                    window.confirm(role === "tutor" ? "Отказаться от заявки?" : "Отказаться от этого предложения?") &&
                    act(() => marketplace.decline(responseId))
                  }
                >
                  Отказаться
                </Button>
              </>
            )}
          </span>
        )}
      </div>
      {active && byMe && !editing && <p className="text-xs text-fg-soft">Ждём ответа: договориться можно о цене, которую предложила другая сторона.</p>}
    </div>
  );
}
