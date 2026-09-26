"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { Avatar, PresenceDot, Rating } from "@/components/tutor-card";
import { Alert, Badge, Button, Spinner } from "@/components/ui";
import { marketplace } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { FORMAT_LABELS, fmtRub, LEVEL_LABELS } from "@/lib/format";
import { useLoad } from "@/lib/hooks";

/** Публичный профиль репетитора: открывается по ссылке «Поделиться» без регистрации. */
export default function TutorPage() {
  const { id } = useParams<{ id: string }>();
  const { status, user } = useAuth();
  const authed = status === "authenticated";
  const tutor = useLoad(() => marketplace.tutor(id, authed), [id, authed]);
  const [copied, setCopied] = useState(false);

  if (tutor.error) return <Alert>{tutor.error}</Alert>;
  if (!tutor.data) return <Spinner />;
  const t = tutor.data;
  const own = user?.id === t.user_id;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {own && !t.published && (
        <Alert kind="info">
          Профиль скрыт из поиска — так его видите только вы. Включить показ можно в{" "}
          <Link href="/dashboard/profile" className="font-medium underline">
            настройках профиля
          </Link>
          .
        </Alert>
      )}
      <div className="flex flex-wrap items-start gap-5">
        <Avatar url={t.photo_url} name={t.full_name} size={96} />
        <div className="min-w-0 flex-1 space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t.full_name}</h1>
          <p>{t.headline}</p>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <Rating rating={t.rating} count={t.reviews_count} />
            {t.education_verified && <Badge tone="ok">образование подтверждено</Badge>}
            <PresenceDot presence={t.presence} />
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {!own && (
          <Button disabled title="Заявки репетиторам — следующий шаг разработки">
            Хочу с вами заниматься
          </Button>
        )}
        <Button
          variant="secondary"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(t.share_url);
              setCopied(true);
            } catch {
              window.prompt("Скопируйте ссылку", t.share_url);
            }
          }}
        >
          {copied ? "Ссылка скопирована" : "Поделиться"}
        </Button>
      </div>

      <section className="grid gap-3 rounded-2xl border border-line bg-surface p-5 text-sm sm:grid-cols-2">
        <p>
          <span className="text-fg-soft">Предметы: </span>
          {t.subjects.map((s) => s.name).join(", ") || "—"}
        </p>
        <p>
          <span className="text-fg-soft">С кем занимается: </span>
          {t.levels.map((l) => LEVEL_LABELS[l]).join(", ") || "—"}
        </p>
        <p>
          <span className="text-fg-soft">Формат: </span>
          {t.formats.map((f) => FORMAT_LABELS[f].toLowerCase()).join(", ") || "—"}
        </p>
        <p>
          <span className="text-fg-soft">Цена: </span>
          {t.price ? `от ${fmtRub(t.price)} за 60 минут` : "по договорённости"}
          <span className="block text-xs text-fg-soft">Итоговую цену предлагает ученик в заявке, договариваетесь в чате.</span>
        </p>
        {t.experience_years !== null && (
          <p>
            <span className="text-fg-soft">Опыт: </span>
            {t.experience_years} лет
          </p>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">О себе</h2>
        <p className="whitespace-pre-line">{t.about || "—"}</p>
      </section>

      {t.education_verified && (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Образование</h2>
          {t.education.length ? (
            <ul className="space-y-1.5">
              {t.education.map((e) => (
                <li key={e.id} className="text-sm">
                  <b>{e.title}</b> — {e.institution}, {e.year}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-fg-soft">
              Документы проверены модератором.{" "}
              <Link href="/login" className="text-brand hover:underline">
                Войдите
              </Link>
              , чтобы увидеть список.
            </p>
          )}
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Отзывы</h2>
        <p className="text-sm text-fg-soft">Отзывов пока нет.</p>
      </section>
    </div>
  );
}
