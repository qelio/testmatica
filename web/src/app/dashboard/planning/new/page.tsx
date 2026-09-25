"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Alert, Button, Field, Select, Spinner } from "@/components/ui";
import { classroom, planning } from "@/lib/api";
import { toDateInput } from "@/lib/dates";
import { errorText, useLoad } from "@/lib/hooks";

export default function NewPlanPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <NewPlan />
    </Suspense>
  );
}

function NewPlan() {
  const router = useRouter();
  const preset = useSearchParams().get("template") ?? "";
  const groups = useLoad(async () => [...(await classroom.groups(false, "school")), ...(await classroom.groups(false, "tutor"))], []);
  const students = useLoad(() => classroom.students(), []);
  const mine = useLoad(() => planning.templates("mine"), []);
  const pub = useLoad(() => planning.templates("public"), []);

  const [targetType, setTargetType] = useState<"group" | "student">("group");
  const [targetId, setTargetId] = useState("");
  const [templateId, setTemplateId] = useState(preset);
  const [title, setTitle] = useState("");
  const [start, setStart] = useState(() => toDateInput(new Date()));
  const [distribute, setDistribute] = useState(true);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <Link href="/dashboard/planning" className="text-sm text-fg-soft hover:text-fg">
        ← Планирование
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">Новый КТП</h1>
      <form
        className="space-y-4 rounded-2xl border border-line bg-surface p-5"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(undefined);
          try {
            const plan = await planning.createPlan({
              target_type: targetType,
              target_id: targetId,
              title: title || null,
              template_id: templateId || null,
              start_date: start || null,
              distribute,
            });
            router.replace(`/dashboard/planning/${plan.id}`);
          } catch (err) {
            setError(errorText(err));
            setBusy(false);
          }
        }}
      >
        {error && <Alert>{error}</Alert>}
        <div className="grid grid-cols-[auto_1fr] items-end gap-3">
          <Select
            label="Для кого"
            value={targetType}
            onChange={(e) => {
              setTargetType(e.target.value as "group" | "student");
              setTargetId("");
            }}
          >
            <option value="group">Класс / группа</option>
            <option value="student">Ученик</option>
          </Select>
          <Select label={targetType === "group" ? "Класс или группа" : "Ученик"} value={targetId} required onChange={(e) => setTargetId(e.target.value)}>
            <option value="">Выберите</option>
            {targetType === "group"
              ? groups.data?.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.title}
                  </option>
                ))
              : students.data
                  ?.filter((s) => s.status === "active")
                  .map((s) => (
                    <option key={s.student_id} value={s.student_id}>
                      {s.full_name}
                    </option>
                  ))}
          </Select>
        </div>
        <Select label="Основа" value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
          <option value="">С нуля — уроки добавлю сам (сразу или по ходу)</option>
          {!!mine.data?.length && (
            <optgroup label="Мои шаблоны">
              {mine.data.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title} · уроков: {t.lessons_count}
                </option>
              ))}
            </optgroup>
          )}
          {!!pub.data?.length && (
            <optgroup label="Библиотека КТП">
              {pub.data
                .filter((t) => !mine.data?.some((m) => m.id === t.id))
                .map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.title} · {t.author_name} · уроков: {t.lessons_count}
                  </option>
                ))}
            </optgroup>
          )}
        </Select>
        <Field label="Название (необязательно)" placeholder="По умолчанию — название шаблона" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
        <Field label="Дата начала" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        {templateId && (
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" checked={distribute} onChange={(e) => setDistribute(e.target.checked)} className="mt-1 h-4 w-4 accent-brand" />
            <span>
              <span className="font-medium">Проставить даты по расписанию</span>
              <span className="block text-fg-soft">Уроки по порядку лягут на занятия этого класса или ученика начиная с даты начала.</span>
            </span>
          </label>
        )}
        <Button type="submit" loading={busy} disabled={!targetId} className="w-full">
          Создать
        </Button>
      </form>
    </div>
  );
}
