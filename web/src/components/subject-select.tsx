"use client";

import { Select } from "@/components/ui";
import { content } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

/** Предмет из справочника (его ведут модераторы). Значение — название предмета. */
export function SubjectSelect({
  value,
  onChange,
  label = "Предмет",
  empty = "Не указан",
}: {
  value: string;
  onChange: (name: string) => void;
  label?: string;
  empty?: string;
}) {
  const subjects = useLoad(() => content.subjects(), []);
  const names = subjects.data?.map((s) => s.name) ?? [];
  return (
    <Select label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{empty}</option>
      {/* Прежнее название, которого уже нет в списке, — чтобы форма не теряла значение. */}
      {value && subjects.data && !names.includes(value) && <option value={value}>{value}</option>}
      {names.map((n) => (
        <option key={n} value={n}>
          {n}
        </option>
      ))}
    </Select>
  );
}
