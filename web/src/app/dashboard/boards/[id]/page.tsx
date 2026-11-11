"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { Alert, Spinner } from "@/components/ui";
import { BoardEditor } from "@/components/whiteboard/board-editor";
import { whiteboard } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export default function BoardPage() {
  const { id } = useParams<{ id: string }>();
  const board = useLoad(() => whiteboard.get(id), [id]);
  if (board.error)
    return (
      <div className="mx-auto max-w-xl space-y-3">
        <Alert>{board.error}</Alert>
        <Link href="/dashboard/boards" className="text-sm text-brand-text hover:underline">
          ← Доски
        </Link>
      </div>
    );
  return board.data ? <BoardEditor key={board.data.id} initial={board.data} /> : <Spinner />;
}
