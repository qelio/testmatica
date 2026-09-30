import type { Metadata } from "next";
import { Inter, Nunito } from "next/font/google";
import Script from "next/script";

import { AuthProvider } from "@/lib/auth";
import { RealtimeProvider } from "@/lib/realtime";
import { THEME_SCRIPT } from "@/lib/theme-script";

import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin", "cyrillic"] });
// Округлый шрифт — для названия в шапке.
const nunito = Nunito({ variable: "--font-nunito", subsets: ["latin", "cyrillic"], weight: ["800", "900"] });

export const metadata: Metadata = {
  title: "ТестМатика",
  description: "Образовательная платформа: школьные классы, репетиторы, библиотека знаний и заданий",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // data-theme ставит скрипт до отрисовки — на сервере его нет, отсюда suppressHydrationWarning.
    <html lang="ru" className={`${inter.variable} ${nunito.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="flex min-h-full flex-col font-sans">
        <Script id="theme" strategy="beforeInteractive">
          {THEME_SCRIPT}
        </Script>
        <AuthProvider>
          <RealtimeProvider>{children}</RealtimeProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
