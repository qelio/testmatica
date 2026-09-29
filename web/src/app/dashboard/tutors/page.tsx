import { TutorSearch } from "@/components/views/tutor-search";

/** Тот же раздел, что на сайте, но внутри кабинета. */
export default function TutorsPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <TutorSearch />
    </div>
  );
}
