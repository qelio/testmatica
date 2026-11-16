import type { Metadata } from "next";
import { GroupOffers } from "@/components/views/group-offers";

export const metadata: Metadata = {
  title: "Набор в группы для онлайн-занятий | ТестМатика",
  description: "Посмотрите открытые наборы в учебные группы. Изучите описания занятий и условия записи.",
  alternates: { canonical: "/groups" },
};

export default function GroupsPage() {
  return <GroupOffers />;
}
