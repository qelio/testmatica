/** Логотип ТестМатика — доска на мольберте с √x. Векторный, обрезан по краям рисунка; цвета — как на исходной картинке. */
export function LogoMark({ className = "h-9 w-auto" }: { className?: string }) {
  return (
    <svg viewBox="0 0 100 124" className={className} aria-hidden>
      {/* задние стойки */}
      <rect x="24" y="0" width="11" height="14" rx="2.5" fill="#e6bf88" />
      <rect x="65" y="0" width="11" height="14" rx="2.5" fill="#e6bf88" />
      {/* перекладина между ножками */}
      <rect x="20" y="94" width="60" height="3.4" rx="1.7" fill="#c8a07c" />
      {/* передние ножки */}
      <path d="M16 74 H26 L21 120 H11 Z" fill="#e6bf88" />
      <path d="M74 74 H84 L89 120 H79 Z" fill="#e6bf88" />
      {/* доска */}
      <rect x="2" y="9" width="96" height="66" rx="5" fill="#00a074" />
      <path
        d="M19.5 38 H27 L33.7 57.5 L40.2 26.5 H72.2 M51.6 34.6 L69.6 57.5 M69.6 34.6 L51.6 57.5"
        fill="none"
        stroke="#fff"
        strokeWidth="4.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* полка и опоры */}
      <rect x="0" y="77" width="100" height="3.6" rx="1.8" fill="#c8a07c" />
      <rect x="7.5" y="119" width="17" height="4" rx="2" fill="#cda37b" />
      <rect x="75.5" y="119" width="17" height="4" rx="2" fill="#cda37b" />
    </svg>
  );
}
