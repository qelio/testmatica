import Link from "next/link";

import { LEGAL, LEGAL_ORDER, legalHref, OPERATOR } from "@/lib/legal";
import { APP_VERSION } from "@/lib/version";

/** Нижняя строка сайта: документы и реквизиты (закон требует держать политику ПД в открытом доступе). */
export function LegalBar({ wide = false }: { wide?: boolean }) {
  return (
    <div className="border-t border-line bg-surface">
      <div className={`mx-auto flex ${wide ? "max-w-[1446px] lg:px-[60px]" : "max-w-6xl"} flex-col gap-2 px-4 py-4 text-xs text-fg-soft sm:px-6`}>
        <p>
          © {new Date().getFullYear()} ТестМатика · {OPERATOR.name}, самозанятый, ИНН {OPERATOR.inn}
        </p>
        <nav className="flex flex-wrap gap-x-4 gap-y-1">
          {LEGAL_ORDER.map((slug) => (
            <Link key={slug} href={legalHref(slug)} className="hover:text-fg">
              {LEGAL[slug].short}
            </Link>
          ))}
        </nav>
        {/* Номер выкладки (решение №65); на локальном стенде его нет. */}
        {APP_VERSION && <p>Версия {APP_VERSION}</p>}
      </div>
    </div>
  );
}
