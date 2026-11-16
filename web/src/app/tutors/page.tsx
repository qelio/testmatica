import type { Metadata } from "next";
import { TutorSearch } from "@/components/views/tutor-search";

export const metadata: Metadata = {
  title: "Найти репетитора для онлайн-занятий | ТестМатика",
  description: "Выберите репетитора для онлайн-занятий по нужному предмету. Сравните анкеты педагогов, опыт и условия занятий.",
  alternates: { canonical: "/tutors" },
};

export default function TutorsPage() {
  return <TutorSearch />;
}
