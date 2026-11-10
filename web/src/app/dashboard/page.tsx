"use client";

import { StudentHome } from "@/components/game";
import { NotificationRow, useNotifications } from "@/components/notifications";
import { TeacherHome } from "@/components/teacher-home";
import { TrialFollowups } from "@/components/trial-followups";
import { Alert } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function DashboardPage() {
  const { user } = useAuth();
  const { items, unread, error, markAllRead, markRead } = useNotifications();

  if (!user) return null;
  const firstName = user.first_name || user.full_name;
  const student = user.roles.includes("student");
  const teacher = user.roles.includes("teacher");

  return (
    <div className={`mx-auto space-y-6 ${student || teacher ? "max-w-6xl" : "max-w-4xl"}`}>
      {student ? (
        <StudentHome user={user} />
      ) : (
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Здравствуйте, {firstName}!</h1>
        </div>
      )}
      {teacher && <TeacherHome />}
      {student && <TrialFollowups />}

      <section className="rounded-2xl border border-line bg-surface">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="font-semibold">
            Уведомления
            {unread > 0 && (
              <span className="ml-2 rounded-full bg-brand px-2 py-0.5 text-xs font-medium text-on-brand">{unread}</span>
            )}
          </h2>
          {unread > 0 && (
            <button
              className="text-sm text-brand-text hover:underline"
              onClick={() => void markAllRead()}
            >
              Прочитать все
            </button>
          )}
        </div>
        {error && (
          <div className="p-5">
            <Alert>{error}</Alert>
          </div>
        )}
        {items === null && !error && <p className="px-5 py-6 text-sm text-fg-soft">Загрузка…</p>}
        {items?.length === 0 && <p className="px-5 py-6 text-sm text-fg-soft">Пока нет уведомлений</p>}
        <ul className="divide-y divide-line">
          {items?.map((n) => (
            <NotificationRow key={n.id} n={n} onOpen={() => void (n.read_at || markRead(n.id))} />
          ))}
        </ul>
      </section>

    </div>
  );
}
