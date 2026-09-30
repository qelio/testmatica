import { GroupOffers } from "@/components/views/group-offers";

/** Наборы в группы (как /groups на сайте), но внутри кабинета ученика. */
export default function FindGroupsPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <GroupOffers />
    </div>
  );
}
