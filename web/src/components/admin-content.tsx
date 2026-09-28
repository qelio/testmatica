"use client";

import { useState } from "react";

import { ReasonModal } from "@/components/reviews";
import { Button } from "@/components/ui";
import { admin, type AdminContentKind } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorText } from "@/lib/hooks";

const TITLES: Record<AdminContentKind, { remove: string; restore: string; hint: string }> = {
  course: { remove: "Снять курс с платформы", restore: "Вернуть курс", hint: "Курс исчезнет из библиотеки и у учеников автора; прогресс учеников сохранится. Автор увидит причину." },
  task: { remove: "Снять задачу с платформы", restore: "Вернуть задачу", hint: "Задача исчезнет из банка; в уже выданных тестах она останется. Автор увидит причину." },
  template: { remove: "Снять шаблон с платформы", restore: "Вернуть шаблон", hint: "Шаблон исчезнет из библиотеки КТП; уже сделанные по нему КТП останутся. Автор увидит причину." },
  offer: { remove: "Снять набор", restore: "", hint: "До запуска набор отменится, записавшиеся получат уведомление; идущая группа продолжит заниматься." },
  tutor: { remove: "Скрыть профиль", restore: "Снять запрет на показ", hint: "Профиль пропадёт из поиска и по ссылке; включить показ педагог не сможет, пока вы не снимете запрет." },
};

/** Кнопки администратора: снять любой контент с платформы без очереди модерации или вернуть. */
export function AdminContentActions({
  kind,
  id,
  removed,
  onChanged,
}: {
  kind: AdminContentKind;
  id: string;
  removed: boolean;
  onChanged: () => void;
}) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  if (!user?.roles.includes("admin")) return null;
  const t = TITLES[kind];
  if (removed && !t.restore) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {removed ? (
        <Button
          variant="secondary"
          loading={busy}
          onClick={async () => {
            setBusy(true);
            setError(undefined);
            try {
              await admin.restoreContent(kind, id);
              onChanged();
            } catch (e) {
              setError(errorText(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          {t.restore}
        </Button>
      ) : (
        <Button variant="ghost" className="text-danger" onClick={() => setOpen(true)}>
          {t.remove}
        </Button>
      )}
      {error && <span className="text-sm text-danger">{error}</span>}
      <ReasonModal
        open={open}
        title={t.remove}
        label="Причина (увидит автор)"
        hint={`${t.hint} Действует сразу, без очереди модерации.`}
        submit={t.remove}
        onClose={() => setOpen(false)}
        onSubmit={async (reason) => {
          await admin.removeContent(kind, id, reason);
          setOpen(false);
          onChanged();
        }}
      />
    </span>
  );
}
