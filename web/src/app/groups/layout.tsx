import { PublicShell } from "@/components/public-shell";

/** Наборы в группы — открыты без регистрации; записаться может вошедший ученик. */
export default function GroupsLayout({ children }: LayoutProps<"/groups">) {
  return <PublicShell>{children}</PublicShell>;
}
