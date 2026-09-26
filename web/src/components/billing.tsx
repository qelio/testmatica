"use client";

import { Badge, Select } from "@/components/ui";

/** Платно или бесплатно. Режимов «учитель/репетитор» нет — это указывается у группы, ученика и занятия. */
export function BillingSelect({
  value,
  onChange,
  label = "Оплата",
  free = "Бесплатно",
  paid = "Платно",
}: {
  value: boolean;
  onChange: (paid: boolean) => void;
  label?: string;
  free?: string;
  paid?: string;
}) {
  return (
    <Select label={label} value={value ? "paid" : "free"} onChange={(e) => onChange(e.target.value === "paid")}>
      <option value="free">{free}</option>
      <option value="paid">{paid}</option>
    </Select>
  );
}

export function PaidBadge({ paid }: { paid: boolean }) {
  return paid ? <Badge tone="warn">платно</Badge> : null;
}
