import { usePathname } from "next/navigation";

/** Репетиторы и наборы в группы есть и на публичном сайте, и в кабинете ученика.
 * Внутри кабинета ссылки между ними ведут в кабинет — чтобы не выходить из него. */
export function useMarketBase(): "" | "/dashboard" {
  return usePathname().startsWith("/dashboard") ? "/dashboard" : "";
}
