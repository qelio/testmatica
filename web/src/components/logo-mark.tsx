import { LOGO_WORD_MATIKA, LOGO_WORD_TEST } from "@/components/logo-word-paths";

/** Геккон из логотипа. Цвета тела и контуров — из токенов: в тёмной теме свои. */
function Gecko() {
  return (
    <>
      <g fill="#157a4c" stroke="#157a4c" strokeWidth="6" strokeLinejoin="round">
        <polygon points="34,132 12,112 32,102" />
        <polygon points="48,92 24,72 52,68" />
        <polygon points="76,46 80,20 98,40" />
      </g>
      <path
        d="M30 192 C20 140 30 90 60 60 C85 35 125 30 150 50 C165 62 172 72 186 76 C202 81 206 100 196 112 C186 124 160 128 135 126 C115 125 106 140 110 192 Z"
        fill="var(--logo-body)"
      />
      <path d="M72 192 C78 158 100 134 136 126 C116 134 108 158 110 192 Z" fill="#9be7b4" />
      <g fill="#b8f04a">
        <rect x="34" y="116" width="13" height="13" rx="3" />
        <rect x="49" y="131" width="13" height="13" rx="3" />
        <rect x="64" y="116" width="13" height="13" rx="3" />
        <rect x="79" y="101" width="13" height="13" rx="3" />
      </g>
      <circle cx="118" cy="74" r="24" fill="#fff" />
      {/* Зрачок и моргание оживают только внутри .tm-live (главная); в остальных местах логотип неподвижен. */}
      <g className="tm-gecko-eye">
        <circle cx="127" cy="80" r="12" fill="var(--logo-ink)" />
        <circle cx="132" cy="75" r="3.5" fill="#fff" />
      </g>
      <circle className="tm-gecko-blink" cx="118" cy="74" r="25" fill="var(--logo-body)" />
      {/* веко: сегмент глаза над линией брови */}
      <path d="M104.11 54.42 A24 24 0 0 1 138.93 62.26 Z" fill="var(--logo-body)" />
      <path d="M90 53 L150 66" stroke="var(--logo-ink)" strokeWidth="7" strokeLinecap="round" fill="none" />
      <ellipse cx="182" cy="88" rx="5" ry="3.2" fill="var(--logo-ink)" transform="rotate(-15 182 88)" />
      <path d="M140 108 Q166 116 192 103" stroke="var(--logo-ink)" strokeWidth="5" strokeLinecap="round" fill="none" />
      <path d="M140 108 Q133 106 132 99" stroke="var(--logo-ink)" strokeWidth="5" strokeLinecap="round" fill="none" />
    </>
  );
}

/** Знак ТестМатики — решительный геккон (решение №64). */
export function LogoMark({ className = "h-9 w-auto" }: { className?: string }) {
  return (
    <svg viewBox="0 0 210 200" className={className} aria-hidden>
      <g className="tm-gecko-hop">
        <Gecko />
      </g>
    </svg>
  );
}

/** Полный логотип (решение №64): надпись огибает геккона. Геометрия — как в макете, рамка обрезана по рисунку. */
export function LogoFull({ className = "h-[52px] w-auto" }: { className?: string }) {
  return (
    <svg viewBox="139 127 919 264" className={className} aria-hidden>
      <path d={LOGO_WORD_TEST} className="fill-logo-word" fillRule="evenodd" />
      <path d={LOGO_WORD_MATIKA} className="fill-leaf" fillRule="evenodd" />
      <g transform="translate(126 102.5) scale(1.5)">
        <g className="tm-gecko-hop">
          <Gecko />
        </g>
      </g>
    </svg>
  );
}
