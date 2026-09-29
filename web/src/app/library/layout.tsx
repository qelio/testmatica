import { PublicShell } from "@/components/public-shell";

/** Публичная библиотека — доступна без регистрации (ТЗ, раздел 9). Шапка — общая для публичных страниц. */
export default function PublicLibraryLayout({ children }: LayoutProps<"/library">) {
  return <PublicShell>{children}</PublicShell>;
}
