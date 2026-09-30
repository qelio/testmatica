import { GroupOfferPage } from "@/components/views/group-offer-page";

/** Страница набора (как /groups/[id] на сайте), но внутри кабинета ученика. */
export default function FindGroupPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <GroupOfferPage />
    </div>
  );
}
