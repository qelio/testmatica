/** Короткий номер задачи перед названием: «(100345) Задание 6» — по нему задачу можно найти в банке. */
export function TaskNumber({ n }: { n: number | undefined }) {
  if (!n) return null;
  return <span className="mr-1.5 font-mono text-fg-soft tabular-nums">({n})</span>;
}
