import { usePathname } from "next/navigation";

/** Репетиторы и наборы в группы есть и на публичном сайте, и в кабинете ученика.
 * Внутри кабинета ссылки между ними ведут в кабинет — чтобы не выходить из него.
 * Наборы в кабинете — /dashboard/find-groups: /dashboard/groups занят классами педагога. */
export function useMarketLinks() {
  const inside = usePathname().startsWith("/dashboard");
  return {
    tutorsBase: inside ? "/dashboard" : "",
    tutor: (id: string) => `${inside ? "/dashboard" : ""}/tutors/${id}`,
    offer: (id: string) => (inside ? `/dashboard/find-groups/${id}` : `/groups/${id}`),
  };
}
