"use client";

import { Field } from "@/components/ui";
import type { PersonName } from "@/lib/api";

export const EMPTY_NAME: PersonName = { last_name: "", first_name: "", middle_name: "" };

/** Части имени из пользователя (или пустые). */
export function nameOf(user?: Partial<PersonName> | null): PersonName {
  return { last_name: user?.last_name ?? "", first_name: user?.first_name ?? "", middle_name: user?.middle_name ?? "" };
}

/** Имя не менялось (с точностью до пробелов). */
export function sameName(a: PersonName, b: Partial<PersonName>): boolean {
  const norm = (v?: string) => (v ?? "").trim().replace(/\s+/g, " ");
  return (["last_name", "first_name", "middle_name"] as const).every((k) => norm(a[k]) === norm(b[k]));
}

/** Части имени из готового «Фамилия Имя Отчество» — когда сервис отдаёт только full_name (списки учеников). */
export function splitFullName(fullName: string): PersonName {
  const [last = "", first = "", ...rest] = fullName.trim().split(/\s+/);
  return { last_name: last, first_name: first, middle_name: rest.join(" ") };
}

/** Фамилия, имя и отчество — отдельными полями (решение №35). В списках имя показывается «Фамилия Имя Отчество». */
export function NameFields({
  value,
  onChange,
  errors = {},
  idPrefix = "name",
  autoComplete = true,
}: {
  value: PersonName;
  onChange: (v: PersonName) => void;
  errors?: Partial<Record<keyof PersonName, string>>;
  idPrefix?: string;
  /** Для своего аккаунта — подсказки браузера; для чужого (ученик, админка) — без них. */
  autoComplete?: boolean;
}) {
  const field = (key: keyof PersonName, label: string, ac: string, required: boolean) => (
    <Field
      id={`${idPrefix}-${key}`}
      name={key}
      label={label}
      required={required}
      maxLength={80}
      autoComplete={autoComplete ? ac : "off"}
      value={value[key]}
      error={errors[key]}
      onChange={(e) => onChange({ ...value, [key]: e.target.value })}
    />
  );
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {field("last_name", "Фамилия", "family-name", true)}
      {field("first_name", "Имя", "given-name", true)}
      {field("middle_name", "Отчество (если есть)", "additional-name", false)}
    </div>
  );
}
