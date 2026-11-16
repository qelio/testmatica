import type { Metadata } from "next";
import { Catalog } from "@/components/library";

export const metadata: Metadata = {
  title: "Библиотека знаний — бесплатные курсы | ТестМатика",
  description: "Изучайте бесплатные онлайн-курсы из библиотеки ТестМатики. Материалы проверены модераторами и доступны без регистрации.",
  alternates: { canonical: "/library" },
};

export default function PublicLibraryPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Библиотека знаний</h1>
        <p className="mt-2 text-fg-soft">Бесплатные курсы, проверенные модераторами. Читать можно без регистрации.</p>
      </div>
      <Catalog base="/library" />
    </div>
  );
}
