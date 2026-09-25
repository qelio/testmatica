"use client";

import { useParams } from "next/navigation";

import { CourseView } from "@/components/course-view";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <CourseView id={id} base="/dashboard/library" />;
}
