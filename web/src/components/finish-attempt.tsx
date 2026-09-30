"use client";

import { useState } from "react";

import { assessment } from "@/lib/api";
import { errorText } from "@/lib/hooks";

/** Педагог завершает работу ученика досрочно — как если бы ученик сдал её сам. */
export function FinishButton({
  attemptId,
  name,
  onDone,
  onError,
  className = "text-sm text-danger hover:underline",
}: {
  attemptId: string;
  name: string;
  onDone: () => void;
  onError: (e: string) => void;
  className?: string;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <button
      type="button"
      className={className}
      disabled={busy}
      onClick={async () => {
        if (!window.confirm(`Завершить работу ученика ${name}? Сохранённые ответы уйдут на проверку, продолжить он не сможет.`)) return;
        setBusy(true);
        try {
          await assessment.finishAttempt(attemptId);
          onDone();
        } catch (e) {
          onError(errorText(e));
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? "Завершаем…" : "Завершить"}
    </button>
  );
}
