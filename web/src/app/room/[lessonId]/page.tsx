"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Spinner } from "@/components/ui";
import { VideoRoomScreen } from "@/components/video-room";
import { useAuth } from "@/lib/auth";

/** Комната занятия — на весь экран, без меню кабинета. */
export default function RoomPage() {
  const { lessonId } = useParams<{ lessonId: string }>();
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);

  if (status !== "authenticated") {
    return (
      <div className="grid min-h-dvh place-items-center">
        <Spinner />
      </div>
    );
  }
  return <VideoRoomScreen lessonId={lessonId} />;
}
