import Link from "next/link";

import { Badge } from "@/components/ui";
import type { TutorCard } from "@/lib/api";
import { FORMAT_LABELS, fmtRating, fmtRub, LEVEL_LABELS, pluralReviews, presenceText } from "@/lib/format";

export function Avatar({ url, name, size = 64 }: { url: string | null; name: string; size?: number }) {
  const initials = name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("");
  return url ? (
    // eslint-disable-next-line @next/next/no-img-element -- временные ссылки S3, оптимизация Next не нужна
    <img src={url} alt={name} width={size} height={size} className="shrink-0 rounded-full object-cover" style={{ width: size, height: size }} />
  ) : (
    <span
      className="grid shrink-0 place-items-center rounded-full bg-brand/15 font-semibold text-brand"
      style={{ width: size, height: size, fontSize: size / 2.6 }}
      aria-hidden
    >
      {initials}
    </span>
  );
}

export function Rating({ rating, count }: { rating: number | null; count: number }) {
  if (rating === null || count === 0) return <span className="text-sm text-fg-soft">нет отзывов</span>;
  return (
    <span className="text-sm">
      <b>★ {fmtRating(rating)}</b>
      <span className="text-fg-soft"> из 10 · {pluralReviews(count)}</span>
    </span>
  );
}

export function PresenceDot({ presence }: { presence: TutorCard["presence"] }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-fg-soft">
      <span className={`h-2 w-2 rounded-full ${presence.online ? "bg-ok" : "bg-line"}`} aria-hidden />
      {presenceText(presence)}
    </span>
  );
}

/** Карточка в списке поиска. */
/** base — «/dashboard», если карточка показана в кабинете. */
export function TutorCardView({ tutor, base = "" }: { tutor: TutorCard; base?: string }) {
  return (
    <Link href={`${base}/tutors/${tutor.user_id}`} className="flex gap-4 rounded-2xl border border-line bg-surface p-5 transition-colors hover:border-brand/50">
      <Avatar url={tutor.photo_url} name={tutor.full_name} />
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h2 className="text-lg font-semibold">{tutor.full_name}</h2>
          {tutor.education_verified && <Badge tone="ok">образование подтверждено</Badge>}
          <PresenceDot presence={tutor.presence} />
        </div>
        <p className="text-sm">{tutor.headline}</p>
        <p className="text-sm text-fg-soft">
          {[
            tutor.subjects.map((s) => s.name).join(", "),
            tutor.levels.map((l) => LEVEL_LABELS[l]).join(", "),
            tutor.formats.map((f) => FORMAT_LABELS[f].toLowerCase()).join(" и "),
            tutor.experience_years ? `опыт ${tutor.experience_years} лет` : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          {tutor.price && <span className="font-semibold">от {fmtRub(tutor.price)} / 60 мин</span>}
          <Rating rating={tutor.rating} count={tutor.reviews_count} />
        </div>
      </div>
    </Link>
  );
}
