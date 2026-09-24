import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { AuthProvider } from "@/lib/auth";
import { RealtimeProvider } from "@/lib/realtime";

import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin", "cyrillic"] });

export const metadata: Metadata = {
  title: "Тестматика",
  description: "Образовательная платформа: школьные классы, репетиторы, библиотека знаний и заданий",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className={`${inter.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">
        <AuthProvider>
          <RealtimeProvider>{children}</RealtimeProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
