// Декоративные элементы главной: мерцающие «пиксели» с тела геккона из логотипа и бегущая строка.

const PIXELS = [
  [0, 1],
  [1, 0],
  [1, 2],
  [2, 1],
  [3, 0],
  [3, 2],
  [4, 1],
];

/** Узор из квадратиков как на спине геккона. */
export function Pixels({ className = "" }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 80 48" className={`pointer-events-none ${className}`}>
      {PIXELS.map(([x, y], i) => (
        <rect key={i} x={x * 16 + 1} y={y * 16 + 1} width="14" height="14" rx="3.5" className="tm-pixel fill-lime" style={{ animationDelay: `${i * 0.35}s` }} />
      ))}
    </svg>
  );
}

// Настоящие темы из открытой библиотеки.
const TOPICS = [
  "Условие Фано",
  "Круги Эйлера",
  "Таблицы истинности",
  "Граф и весовая матрица",
  "Запросы к базе данных",
  "Системы счисления",
  "Программирование на Python",
  "Создаём сайты на HTML и CSS",
  "Поисковые запросы",
  "Линейные уравнения",
];

export function TopicsMarquee() {
  return (
    <div aria-hidden className="tm-marquee-mask overflow-hidden border-y border-line py-4">
      <div className="tm-marquee flex w-max">
        {[0, 1].map((copy) => (
          <div key={copy} className="flex shrink-0 items-center">
            {TOPICS.map((t) => (
              <span key={t} className="flex items-center text-xl font-semibold whitespace-nowrap text-fg-soft">
                <span className="mx-7 h-2.5 w-2.5 rounded-[3px] bg-lime" />
                {t}
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
