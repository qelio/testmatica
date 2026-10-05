"use client";

import { useState } from "react";

import { Alert, Button, Field } from "@/components/ui";
import { identity } from "@/lib/api";
import { fmtDateTime } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

/** Адрес подключения для Claude — на том же домене, что и сайт. */
function mcpUrl(): string {
  return typeof window === "undefined" ? "/api/mcp" : `${window.location.origin}/api/mcp`;
}

/** Подключение Claude (решение №41): личные ключи доступа и как подключить. Claude создаёт задачи и теорию от вашего имени. */
export function ClaudeConnect() {
  const keys = useLoad(() => identity.apiKeys(), []);
  const [name, setName] = useState("Claude Desktop");
  const [created, setCreated] = useState<string | null>(null);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  async function copy(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
    } catch {
      setCopied(null);
    }
  }

  return (
    <section className="space-y-4 rounded-2xl border border-line bg-surface p-5">
      <div>
        <h2 className="font-semibold">Подключение Claude</h2>
        <p className="text-sm text-fg-soft">
          Claude сможет сам создавать задачи в вашем банке и теорию в библиотеке: «сделай 15 задач на квадратные уравнения с разбором» —
          и задачи появятся у вас как личные. В публичный банк — как обычно, через модерацию.
        </p>
      </div>
      {error && <Alert>{error}</Alert>}

      {created ? (
        <div className="space-y-3 rounded-xl border border-brand/40 bg-brand/5 p-4 text-sm">
          <p className="font-medium">Ключ создан — скопируйте его сейчас, потом он показан не будет.</p>
          <div className="flex flex-wrap items-center gap-2">
            <code className="min-w-0 flex-1 break-all rounded-lg bg-surface px-3 py-2 font-mono text-xs">{created}</code>
            <Button variant="secondary" className="h-9" onClick={() => copy(created, "key")}>
              {copied === "key" ? "Скопировано" : "Копировать"}
            </Button>
          </div>
          <ol className="list-inside list-decimal space-y-1.5 text-fg-soft">
            <li>
              В Claude Desktop откройте <b className="text-fg">Настройки → Коннекторы → Добавить свой коннектор</b> (Customize → Connectors →
              Add custom connector).
            </li>
            <li>
              Название — «ТестМатика», адрес —{" "}
              <button type="button" onClick={() => copy(mcpUrl(), "url")} className="font-mono text-brand hover:underline">
                {mcpUrl()}
              </button>
              {copied === "url" && " (скопировано)"}.
            </li>
            <li>
              В заголовках запроса (Request headers) добавьте <code className="font-mono text-fg">Authorization</code> со значением{" "}
              <code className="font-mono text-fg">Bearer {created.slice(0, 11)}…</code> — то есть «Bearer» и пробел перед ключом.
            </li>
            <li>Напишите Claude, например: «Посмотри рубрикатор по алгебре и создай 5 задач на линейные уравнения с разбором».</li>
          </ol>
          <Button variant="ghost" className="h-9" onClick={() => setCreated(null)}>
            Готово
          </Button>
        </div>
      ) : (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(undefined);
            try {
              const res = await identity.createApiKey(name);
              setCreated(res.key);
              setCopied(null);
              keys.reload();
            } catch (err) {
              setError(errorText(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          <div className="min-w-48 flex-1">
            <Field label="Название ключа" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <Button type="submit" loading={busy} className="h-11">
            Выпустить ключ
          </Button>
        </form>
      )}

      {!!keys.data?.length && (
        <ul className="divide-y divide-line rounded-xl border border-line">
          {keys.data.map((k) => (
            <li key={k.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-sm">
              <span className="min-w-0 flex-1">
                <span className="font-medium">{k.name}</span> <span className="font-mono text-xs text-fg-soft">{k.prefix}…</span>
                <span className="block text-xs text-fg-soft">
                  выпущен {fmtDateTime(k.created_at)} · {k.last_used_at ? `использовался ${fmtDateTime(k.last_used_at)}` : "ещё не использовался"}
                </span>
              </span>
              <button
                type="button"
                className="text-sm text-fg-soft hover:text-danger"
                onClick={async () => {
                  if (!window.confirm(`Отозвать ключ «${k.name}»? Claude с ним больше не сможет работать.`)) return;
                  try {
                    await identity.revokeApiKey(k.id);
                    keys.reload();
                  } catch (err) {
                    setError(errorText(err));
                  }
                }}
              >
                Отозвать
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
