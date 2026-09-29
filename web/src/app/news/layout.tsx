import { PublicShell } from "@/components/public-shell";

/** Новости платформы — открыты без регистрации. */
export default function NewsLayout({ children }: LayoutProps<"/news">) {
  return <PublicShell>{children}</PublicShell>;
}
