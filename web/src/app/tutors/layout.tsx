import { PublicShell } from "@/components/public-shell";

/** Поиск репетиторов и их профили — открыты без регистрации (ТЗ, раздел 3–4). */
export default function TutorsLayout({ children }: LayoutProps<"/tutors">) {
  return <PublicShell>{children}</PublicShell>;
}
