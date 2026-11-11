"use client";

import Link from "next/link";
import { useState } from "react";

import { LogoMark } from "@/components/logo-mark";
import { confetti } from "@/lib/confetti";

// Настоящие задачи из открытой библиотеки: ссылка ведёт на полный разбор.
const TASKS = [
  {
    tab: "ЕГЭ · задание 4",
    topic: "Префиксный код и условие Фано",
    href: "/library/module/01a12fd1-3b62-7f28-bd08-c7f5d45480ff",
    answer: "14",
    text: "По каналу связи передаются сообщения, содержащие только семь букв: А, Б, Г, И, М, Р, Я. Используется двоичный код, удовлетворяющий условию Фано. Известны коды: А — 010, Б — 011, Г — 100. Какое наименьшее количество двоичных знаков потребуется для кодирования слова МАГИЯ?",
    table: null,
  },
  {
    tab: "ОГЭ · задание 8",
    topic: "Круги Эйлера и поисковые запросы",
    href: "/library/module/01a1393a-49eb-7756-9ee3-84464661883a",
    answer: "20",
    text: "Какое количество страниц (в тысячах) будет найдено по запросу Угол & Прямая?",
    table: [
      ["Угол | Прямая", "380"],
      ["Угол", "180"],
      ["Прямая", "220"],
    ],
  },
];

type Verdict = "right" | "wrong" | null;

export function LandingTasks() {
  const [index, setIndex] = useState(0);
  const [value, setValue] = useState("");
  const [verdict, setVerdict] = useState<Verdict>(null);
  const task = TASKS[index];

  return (
    <div className="tm-reveal relative rounded-3xl border border-line bg-surface">
      {/* Геккон выглядывает из-за карточки и радуется верному ответу. */}
      <LogoMark
        className={`pointer-events-none absolute right-8 bottom-full -z-10 h-20 w-auto origin-bottom transition-transform duration-300 ease-out sm:h-24 ${verdict === "right" ? "translate-y-1 scale-125" : "translate-y-9"}`}
      />
      <div role="tablist" aria-label="Примеры задач" className="flex gap-1 border-b border-line px-3 pt-3 sm:px-6">
        {TASKS.map((t, i) => (
          <button
            key={t.tab}
            type="button"
            role="tab"
            aria-selected={i === index}
            onClick={() => {
              setIndex(i);
              setValue("");
              setVerdict(null);
            }}
            className={`-mb-px border-b-2 px-3 py-2.5 text-sm font-semibold sm:px-4 ${i === index ? "border-brand text-fg" : "border-transparent text-fg-soft hover:text-fg"}`}
          >
            {t.tab}
          </button>
        ))}
      </div>
      <div className="p-5 sm:p-8">
        <p className="text-sm text-fg-soft">{task.topic}</p>
        {task.table && (
          <table className="mt-4 w-full max-w-md text-left text-sm">
            <thead>
              <tr className="border-b border-line text-fg-soft">
                <th className="py-2 pr-4 font-medium">Запрос</th>
                <th className="py-2 font-medium">Найдено страниц (в тысячах)</th>
              </tr>
            </thead>
            <tbody>
              {task.table.map(([query, found]) => (
                <tr key={query} className="border-b border-line/60">
                  <td className="py-2 pr-4 font-mono">{query}</td>
                  <td className="py-2">{found}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="mt-4 max-w-3xl text-lg leading-relaxed">{task.text}</p>
        <form
          className="mt-6 flex flex-wrap items-center gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!value.trim()) return;
            const right = value.trim() === task.answer;
            setVerdict(right ? "right" : "wrong");
            if (right) confetti({ tokens: ["--brand", "--pink", "--sun", "--sky", "--mint"] });
          }}
        >
          <input
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              setVerdict(null);
            }}
            inputMode="numeric"
            maxLength={12}
            aria-label="Ответ"
            placeholder="Ответ"
            autoComplete="off"
            className="h-12 w-32 rounded-xl border border-line bg-bg px-4 text-lg outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
          />
          <button type="submit" className="h-12 rounded-xl bg-brand px-6 font-semibold text-on-brand hover:bg-brand-strong">
            Проверить
          </button>
          <span role="status" className="font-semibold">
            {verdict === "right" && <span className="tm-pop inline-block text-ok">Верно!</span>}
            {verdict === "wrong" && <span className="text-danger">Пока неверно, попробуйте ещё раз</span>}
          </span>
        </form>
        <Link href={task.href} className="mt-5 inline-block font-semibold text-brand-text hover:underline">
          Открыть разбор и другие задачи темы →
        </Link>
      </div>
    </div>
  );
}
