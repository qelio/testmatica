"""Обработчики сообщений из RabbitMQ."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from . import mailer
from .models import EmailDelivery, Notification
from .templates import render

log = logging.getLogger(__name__)


async def on_email_command(envelope: Envelope, session: AsyncSession) -> None:
    """Команда notification.email.send: {"to", "template", "params"}."""
    data = envelope.data
    subject, text, html = render(data["template"], data.get("params", {}))
    session.add(EmailDelivery(command_id=envelope.event_id, to=data["to"], template=data["template"]))
    # Запись о доставке сохраняется в одной транзакции с inbox уже после отправки:
    # если отправка упадёт, сообщение уйдёт на повтор.
    await mailer.send_email(data["to"], subject, text, html)
    log.info("email sent", extra={"template": data["template"], "command_id": str(envelope.event_id)})


async def on_identity_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type == "identity.user.email_verified":
        session.add(
            Notification(
                user_id=UUID(envelope.data["user_id"]),
                kind="welcome",
                title="Добро пожаловать в Тестматику!",
                body="Ваш email подтверждён. Здесь будут появляться уведомления о занятиях, заданиях и сообщениях.",
            )
        )


async def on_classroom_event(envelope: Envelope, session: AsyncSession) -> None:
    data = envelope.data
    if envelope.type == "classroom.link.requested":
        session.add(
            Notification(
                user_id=UUID(data["student_id"]),
                kind="link_request",
                title=f"{data['teacher_name']} хочет добавить вас в свои ученики",
                body="Подтвердите или отклоните запрос в разделе «Мои педагоги».",
                payload={"link_id": data["link_id"], "teacher_id": data["teacher_id"]},
            )
        )
    elif envelope.type == "classroom.link.created" and data["source"] in ("request", "invite"):
        what = "ваш запрос" if data["source"] == "request" else "ваше приглашение"
        session.add(
            Notification(
                user_id=UUID(data["teacher_id"]),
                kind="link_accepted",
                title=f"{data['student_name']} принял(а) {what}",
                body="Ученик появился в списке ваших учеников.",
                payload={"student_id": data["student_id"]},
            )
        )
    elif envelope.type == "classroom.link.declined":
        session.add(
            Notification(
                user_id=UUID(data["teacher_id"]),
                kind="link_declined",
                title=f"{data['student_name']} отклонил(а) ваш запрос",
                payload={"student_id": data["student_id"]},
            )
        )


def _lesson_label(data: dict, for_teacher: bool) -> str:
    """Педагогу — группа или имя ученика, ученику — группа или имя педагога."""
    if data["kind"] == "group" or for_teacher:
        return data["title"]
    return data["teacher_name"]


async def on_schedule_event(envelope: Envelope, session: AsyncSession) -> None:
    data = envelope.data
    teacher = UUID(data["teacher_id"])
    students = [UUID(s) for s in data["student_ids"]]
    actor = envelope.actor_id
    payload = {"lesson_id": data["lesson_ids"][0], "starts_at": data["starts_at"]}

    def notify(user_ids, kind: str, title, body: str = "", extra: dict | None = None, skip_actor: bool = True) -> None:
        """title — функция (для_педагога: bool) -> str. Автора действия не уведомляем."""
        for uid in user_ids:
            if skip_actor and uid == actor:
                continue
            text = title(uid == teacher)
            session.add(
                Notification(user_id=uid, kind=kind, title=text, body=body, payload=payload | (extra or {}))
            )

    count = data["count"]
    t = envelope.type
    if t == "schedule.lesson.created":
        notify(
            students,
            "lesson_created",
            lambda _: f"Новое занятие: {_lesson_label(data, False)}"
            if count == 1
            else f"Новое расписание: {_lesson_label(data, False)} — {count} занятий",
            data.get("subject") or "",
        )
    elif t == "schedule.lesson.cancelled":
        notify(
            [teacher, *students],
            "lesson_cancelled",
            lambda for_teacher: f"Занятие отменено: {_lesson_label(data, for_teacher)}"
            if count == 1
            else f"Отменено занятий: {count} — {_lesson_label(data, for_teacher)}",
            data.get("reason") or "",
        )
    elif t == "schedule.lesson.rescheduled":
        notify(
            [teacher, *students],
            "lesson_rescheduled",
            lambda for_teacher: f"Занятие перенесено: {_lesson_label(data, for_teacher)}",
            "Новое время — в расписании.",
            {"old_starts_at": data["old_starts_at"]},
        )
    elif t == "schedule.lesson.updated":
        notify(students, "lesson_updated", lambda _: f"Изменения в расписании: {_lesson_label(data, False)}")
    elif t == "schedule.reschedule.requested":
        # Индивидуальное занятие: автор — педагог или ученик (title события — имя ученика).
        who = data["teacher_name"] if data["by_teacher"] else data["title"]
        notify(
            [teacher, *students],
            "reschedule_requested",
            lambda _: f"{who} предлагает перенести занятие",
            "Подтвердите или отклоните перенос в расписании.",
            {"new_starts_at": data["new_starts_at"], "request_id": data["request_id"]},
        )
    elif t == "schedule.reschedule.declined":
        notify(
            [UUID(data["requested_by"])],
            "reschedule_declined",
            lambda for_teacher: f"Перенос не согласован: {_lesson_label(data, for_teacher)}",
        )
    elif t == "schedule.lesson.reminder":
        hours = data["hours"]
        when = "Завтра" if hours >= 24 else f"Через {hours} ч"
        notify(
            [teacher, *students],
            "lesson_reminder",
            lambda for_teacher: f"{when} занятие: {_lesson_label(data, for_teacher)}",
            skip_actor=False,
        )


async def on_academic_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type != "academic.grade.created":
        return
    data = envelope.data
    subject = f" — {data['subject']}" if data.get("subject") else ""
    session.add(
        Notification(
            user_id=UUID(data["student_id"]),
            kind="grade",
            title=f"Новая оценка: {data['value']}{subject}",
            body=f"{data['grade_type']}. {data['comment']}",
            payload={"grade_id": data["grade_id"], "starts_at": data["lesson_starts_at"], "teacher_name": data["teacher_name"]},
        )
    )


async def on_inapp_command(envelope: Envelope, session: AsyncSession) -> None:
    """Команда notification.inapp.send: {"user_ids", "kind", "title", "body", "payload", "coalesce_key"}.

    С coalesce_key непрочитанное уведомление с тем же ключом обновляется, а не дублируется
    (одно уведомление на чат, а не на каждое сообщение)."""
    data = envelope.data
    key = data.get("coalesce_key")
    payload = dict(data.get("payload") or {})
    if key:
        payload["coalesce_key"] = key
    for raw in data["user_ids"]:
        user_id = UUID(raw)
        existing = None
        if key:
            existing = (
                await session.execute(
                    select(Notification)
                    .where(
                        Notification.user_id == user_id,
                        Notification.read_at.is_(None),
                        Notification.payload["coalesce_key"].astext == key,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
        if existing is not None:
            existing.title = data["title"]
            existing.body = data.get("body", "")
            existing.created_at = envelope.occurred_at
        else:
            session.add(
                Notification(
                    user_id=user_id, kind=data["kind"], title=data["title"], body=data.get("body", ""), payload=payload
                )
            )


async def on_content_event(envelope: Envelope, session: AsyncSession) -> None:
    """Автору — решение по курсу, отправленному в публичную библиотеку."""
    d = envelope.data
    if envelope.type == "content.course.published" and envelope.actor_id != UUID(d["author_id"]):
        session.add(
            Notification(
                user_id=UUID(d["author_id"]),
                kind="course_published",
                title=f"Курс «{d['title']}» опубликован",
                body="Курс прошёл проверку и появился в публичной библиотеке.",
                payload={"course_id": d["course_id"]},
            )
        )
    elif envelope.type == "content.course.rejected":
        session.add(
            Notification(
                user_id=UUID(d["author_id"]),
                kind="course_rejected",
                title=f"Курс «{d['title']}» не прошёл проверку",
                body=d.get("comment") or "",
                payload={"course_id": d["course_id"]},
            )
        )
