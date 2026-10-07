"use client";

import { useState } from "react";

import { Alert, Button, Field } from "@/components/ui";
import { identity } from "@/lib/api";
import { fmtDateTime } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

/** Адрес подключения для Claude — на том же домене, что и сайт; ключ — в конце адреса (у «своего коннектора»
 *  Claude указывается только адрес, заголовков нет). */
function mcpUrl(key: string): string {
  return `${typeof window === "undefined" ? "" : window.location.origin}/api/mcp/${key}`;
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
          <p className="font-medium">Ключ создан. Скопируйте адрес подключения сейчас — потом ключ показан не будет.</p>
          <div className="flex flex-wrap items-center gap-2">
            <code className="min-w-0 flex-1 break-all rounded-lg bg-surface px-3 py-2 font-mono text-xs">{mcpUrl(created)}</code>
            <Button variant="secondary" className="h-9" onClick={() => copy(mcpUrl(created), "url")}>
              {copied === "url" ? "Скопировано" : "Копировать"}
            </Button>
          </div>
          <ol className="list-inside list-decimal space-y-1.5 text-fg-soft">
            <li>
              В Claude (приложение или claude.ai) откройте <b className="text-fg">Настройки → Коннекторы → Добавить свой коннектор</b>{" "}
              (Settings → Connectors → Add custom connector).
            </li>
            <li>
              Название — «ТестМатика», адрес — скопированный выше (с ключом в конце). Поля OAuth в дополнительных настройках оставьте
              пустыми.
            </li>
            <li>Напишите Claude, например: «Посмотри рубрикатор по алгебре и создай 5 задач на линейные уравнения с разбором».</li>
          </ol>
          <p className="text-xs text-fg-soft">Адрес с ключом — как пароль: не пересылайте его. Если он утёк, отзовите ключ ниже и выпустите новый.</p>
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
