import { PublicShell } from "@/components/public-shell";

/** Юридические документы — открыты без регистрации. */
export default function LegalLayout({ children }: LayoutProps<"/legal">) {
  return <PublicShell>{children}</PublicShell>;
}
