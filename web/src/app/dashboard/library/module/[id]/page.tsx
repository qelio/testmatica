"use client";

import { useParams } from "next/navigation";

import { ModuleView } from "@/components/module-view";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <ModuleView id={id} base="/dashboard/library" />;
}
