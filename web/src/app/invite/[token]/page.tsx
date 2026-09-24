"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Card, Logo, Spinner } from "@/components/ui";
import { classroom } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorText, useLoad } from "@/lib/hooks";
import { clearNext, rememberNext } from "@/lib/next-path";

const STATUS_TEXT = {
  expired: "Срок действия приглашения истёк. Попросите педагога отправить новое.",
  used: "Это приглашение уже использовано.",
  revoked: "Педагог отменил это приглашение.",
};

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const auth = useAuth();
  const invitation = useLoad(() => classroom.viewInvitation(token), [token]);
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);

  const inv = invitation.data;

  async function accept() {
    setLoading(true);
    setError(undefined);
    try {
      await classroom.acceptInvitation(token);
      clearNext();
      router.replace("/dashboard/teachers");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }

  function goAuth(path: "/login" | "/register") {
    rememberNext(`/invite/${token}`);
    router.push(path);
  }

  return (
    <div className="flex flex-1 flex-col items-center px-4 py-10 sm:py-16">
      <Logo className="mb-8" />
      <Card className="w-full max-w-md space-y-5">
        {invitation.error && <Alert>{invitation.error}</Alert>}
        {!inv && !invitation.error && <Spinner />}
        {inv && (
          <>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Приглашение</h1>
              <p className="mt-2 text-fg-soft">
                <b className="text-fg">{inv.teacher_name}</b> приглашает вас заниматься
                {inv.group_title ? (
                  <>
                    {" "}
                    {inv.group_kind === "class" ? "в классе" : "в группе"}{" "}
                    <b className="text-fg">«{inv.group_title}»</b>
                  </>
                ) : null}
                .
              </p>
            </div>
            {inv.status !== "valid" ? (
              <Alert kind="info">{STATUS_TEXT[inv.status]}</Alert>
            ) : auth.status === "loading" ? (
              <Spinner />
            ) : auth.status === "anonymous" ? (
              <div className="space-y-2">
                <Button className="w-full" onClick={() => goAuth("/register")}>
                  Зарегистрироваться и принять
                </Button>
                <Button variant="secondary" className="w-full" onClick={() => goAuth("/login")}>
                  У меня уже есть аккаунт
                </Button>
              </div>
            ) : auth.user.roles.includes("student") ? (
              <>
                {error && <Alert>{error}</Alert>}
                <p className="text-sm text-fg-soft">Вы вошли как {auth.user.full_name}.</p>
                <Button className="w-full" loading={loading} onClick={accept}>
                  Принять приглашение
                </Button>
              </>
            ) : (
              <Alert kind="info">
                Приглашение предназначено для ученика, а вы вошли как педагог. Выйдите и войдите под аккаунтом ученика.
              </Alert>
            )}
            <p className="text-center text-sm">
              <Link href="/" className="text-fg-soft hover:text-fg">
                На главную
              </Link>
            </p>
          </>
        )}
      </Card>
    </div>
  );
}
