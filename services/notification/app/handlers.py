"""Обработчики сообщений из RabbitMQ."""

import logging
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

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
    data = envelope.data
    if envelope.type == "academic.plan_template.published" and envelope.actor_id != UUID(data["author_id"]):
        session.add(Notification(user_id=UUID(data["author_id"]), kind="plan_template_published",
                                 title=f"КТП «{data['title']}» опубликовано в библиотеке", payload={"template_id": data["template_id"]}))
        return
    if envelope.type == "academic.plan_template.rejected":
        session.add(Notification(user_id=UUID(data["author_id"]), kind="plan_template_rejected",
                                 title=f"КТП «{data['title']}» не прошло проверку", body=data.get("comment") or "",
                                 payload={"template_id": data["template_id"]}))
        return
    if envelope.type != "academic.grade.created":
        return
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


async def on_assessment_event(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    t = envelope.type
    if t == "assessment.task.published" and envelope.actor_id != UUID(d["author_id"]):
        session.add(Notification(user_id=UUID(d["author_id"]), kind="task_published",
                                 title=f"Задача «{d['title']}» опубликована в банке", payload={"task_id": d["task_id"]}))
    elif t == "assessment.task.rejected":
        session.add(Notification(user_id=UUID(d["author_id"]), kind="task_rejected",
                                 title=f"Задача «{d['title']}» не прошла проверку", body=d.get("comment") or "",
                                 payload={"task_id": d["task_id"]}))
    elif t == "assessment.submission.reviewed" and d.get("context_type") != "assignment":
        # Ответ из теста или ДЗ — ученик узнает итог всей работы (assessment.attempt.graded).
        percent = round(float(d["score"]) * 100)
        session.add(Notification(user_id=UUID(d["student_id"]), kind="submission_reviewed",
                                 title=f"Педагог проверил решение: «{d['task_title']}» — {percent}%", body=d.get("comment") or "",
                                 payload={"submission_id": d["submission_id"], "task_id": d["task_id"]}))
    elif t == "assessment.assignment.created":
        title = {"live": "Тест на уроке", "homework": "Новое ДЗ", "test": "Новый тест"}.get(d["kind"], "Новый тест")
        # Время открытия и дедлайн — в payload: интерфейс покажет их в часовом поясе ученика.
        for sid in d["student_ids"]:
            session.add(Notification(user_id=UUID(sid), kind="assignment_created", title=f"{title}: «{d['title']}»",
                                     payload={"assignment_id": d["assignment_id"], "deadline": d.get("deadline"),
                                              "opens_at": d.get("opens_at")}))
    elif t == "assessment.assignment.reassigned":
        session.add(Notification(user_id=UUID(d["student_id"]), kind="assignment_reassigned",
                                 title=f"Педагог разрешил пройти ещё раз: «{d['title']}»",
                                 payload={"assignment_id": d["assignment_id"], "deadline": d.get("deadline")}))
    elif t == "assessment.attempt.graded" and not d.get("to_journal"):
        # Если оценка уходит в журнал, ученик получит уведомление об оценке от academic.
        session.add(Notification(user_id=UUID(d["student_id"]), kind="attempt_graded",
                                 title=f"Работа проверена: «{d['title']}» — {d['percent']:g}%, оценка {d['grade']}",
                                 payload={"assignment_id": d["assignment_id"], "attempt_id": d["attempt_id"]}))


async def on_video_event(envelope: Envelope, session: AsyncSession) -> None:
    """Запись занятия готова — педагогу и ученикам занятия."""
    if envelope.type != "video.recording.ready":
        return
    d = envelope.data
    for uid in {d["teacher_id"], *d["viewer_ids"]}:
        session.add(Notification(user_id=UUID(uid), kind="recording_ready", title=f"Запись занятия готова: {d['title']}",
                                 body="Смотреть и скачать можно в карточке занятия. Запись хранится 14 дней.",
                                 payload={"recording_id": d["recording_id"], "lesson_id": d["lesson_id"]}))


def _rub(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " ₽"


async def on_marketplace_event(envelope: Envelope, session: AsyncSession) -> None:
    """Документы об образовании, заявки, отклики и «Договорились»."""
    d = envelope.data
    t = envelope.type
    if t == "marketplace.request.created":
        terms = f"{_rub(d['price'])} за {d['duration_min']} мин"
        for tid in d["tutor_ids"]:
            if d["direct"]:
                session.add(Notification(user_id=UUID(tid), kind="request_direct", title=f"Ученик хочет заниматься с вами: {d['subject']}",
                                         body=f"Предлагает {terms}. Ответьте в чате переговоров.",
                                         payload={"conversation_id": d.get("response_id"), "request_id": d["request_id"]}))
            else:
                session.add(Notification(user_id=UUID(tid), kind="request_open", title=f"Новая заявка: {d['subject']}",
                                         body=f"Ученик предлагает {terms}.", payload={"request_id": d["request_id"]}))
        return
    if t == "marketplace.response.created" and not d.get("direct"):
        session.add(Notification(user_id=UUID(d["student_id"]), kind="response_new", title=f"Новый отклик на заявку: {d['subject']}",
                                 body=f"Репетитор готов заниматься за {_rub(d['price'])}.", payload={"conversation_id": d["response_id"]}))
        return
    if t == "marketplace.deal.agreed":
        for uid in (d["student_id"], d["tutor_id"]):
            session.add(Notification(user_id=UUID(uid), kind="deal_agreed", title=f"Договорились: {d['subject']}",
                                     body=f"{_rub(d['price'])} за {d['duration_min']} мин. Занятия можно ставить в расписание.",
                                     payload={"conversation_id": d["response_id"]}))
        return
    if t == "marketplace.response.closed" and d.get("reason") == "agreed_other":
        session.add(Notification(user_id=UUID(d["tutor_id"]), kind="deal_lost", title=f"Ученик выбрал другого репетитора: {d['subject']}",
                                 payload={"conversation_id": d["response_id"]}))
        return
    if t == "marketplace.request.expired":
        session.add(Notification(user_id=UUID(d["student_id"]), kind="request_expired", title=f"Заявка закрылась: {d['subject']}",
                                 body="Прошло 14 дней. Можно создать новую.", payload={"request_id": d["request_id"]}))
        return
    if t.startswith("marketplace.review."):
        _review_notification(session, t, d)
        return
    if t.startswith(("marketplace.group_offer.", "marketplace.trial.")):
        _offer_notification(session, t, d)
        return
    if t == "marketplace.education.approved":
        session.add(Notification(user_id=UUID(d["user_id"]), kind="education_approved",
                                 title=f"Документ «{d['title']}» подтверждён",
                                 body="В профиле появился бейдж «Образование подтверждено».", payload={"doc_id": d["doc_id"]}))
    elif t == "marketplace.education.rejected":
        session.add(Notification(user_id=UUID(d["user_id"]), kind="education_rejected",
                                 title=f"Документ «{d['title']}» не принят", body=d.get("comment") or "",
                                 payload={"doc_id": d["doc_id"]}))


def _review_notification(session: AsyncSession, t: str, d: dict) -> None:
    """Отзывы: автору — решение модератора, педагогу — новый отзыв, решение по ответу и спору.
    href в payload — куда ведёт уведомление в интерфейсе."""
    tutor, student = UUID(d["tutor_id"]), UUID(d["student_id"])
    to_student = {"review_id": d["review_id"], "href": f"/tutors/{d['tutor_id']}#reviews"}
    to_tutor = {"review_id": d["review_id"], "href": "/dashboard/profile#reviews"}
    comment = d.get("comment") or ""
    add = session.add
    if t == "marketplace.review.approved":
        add(Notification(user_id=student, kind="review_approved", title=f"Ваш отзыв о педагоге {d['tutor_name']} опубликован",
                         payload=to_student))
        add(Notification(user_id=tutor, kind="review_new", title=f"Новый отзыв: {d['rating']}/10 от {d['student_name']}",
                         body="Можно ответить публично или оспорить отзыв.", payload=to_tutor))
    elif t == "marketplace.review.rejected":
        add(Notification(user_id=student, kind="review_rejected", title=f"Отзыв о педагоге {d['tutor_name']} не опубликован",
                         body=comment, payload=to_student))
    elif t == "marketplace.review.removed":
        add(Notification(user_id=student, kind="review_removed", title=f"Модератор удалил ваш отзыв о педагоге {d['tutor_name']}",
                         body=comment, payload=to_student))
    elif t == "marketplace.review.reply_approved":
        add(Notification(user_id=tutor, kind="review_reply_approved", title=f"Ваш ответ на отзыв {d['student_name']} опубликован",
                         payload=to_tutor))
        add(Notification(user_id=student, kind="review_reply_new", title=f"Педагог {d['tutor_name']} ответил на ваш отзыв",
                         payload=to_student))
    elif t == "marketplace.review.reply_rejected":
        add(Notification(user_id=tutor, kind="review_reply_rejected", title=f"Ответ на отзыв {d['student_name']} не опубликован",
                         body=comment, payload=to_tutor))
    elif t == "marketplace.review.dispute_resolved":
        title = "Спор по отзыву решён: отзыв удалён" if d["upheld"] else "Спор по отзыву решён: отзыв оставлен"
        add(Notification(user_id=tutor, kind="review_dispute_resolved", title=title, body=comment,
                         payload=to_tutor | {"conversation_id": d["dispute_id"]}))


def _date(iso: str) -> str:
    """Дата окончания периода для текста уведомления (по Москве — часовой пояс педагога здесь неизвестен)."""
    d = datetime.fromisoformat(iso).astimezone(ZoneInfo("Europe/Moscow"))
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    return f"{d.day} {months[d.month - 1]}"


async def on_billing_event(envelope: Envelope, session: AsyncSession) -> None:
    """Подписка педагога: оплачена, продлена, скоро закончится, закончилась, не удалось продлить."""
    d, t = envelope.data, envelope.type
    user = UUID(d["user_id"])
    link = {"href": "/dashboard/subscription"}
    if t == "billing.subscription.changed":
        reason = d.get("reason")
        if reason == "purchased":
            session.add(Notification(user_id=user, kind="subscription_started", title="Тариф «Базовый» подключён",
                                     body=f"Действует до {_date(d['period_end'])}. Все ограничения бесплатного тарифа сняты.",
                                     payload=link))
        elif reason == "renewed":
            session.add(Notification(user_id=user, kind="subscription_renewed", title="Подписка продлена",
                                     body=f"Тариф «Базовый» действует до {_date(d['period_end'])}.", payload=link))
        elif reason == "expired":
            session.add(Notification(user_id=user, kind="subscription_expired", title="Подписка закончилась",
                                     body="Снова действуют ограничения бесплатного тарифа. Продлить можно в разделе «Тариф».",
                                     payload=link))
    elif t == "billing.subscription.expiring":
        session.add(Notification(user_id=user, kind="subscription_expiring", title="Подписка скоро закончится",
                                 body=f"Тариф «Базовый» действует до {_date(d['period_end'])}, автопродление выключено.",
                                 payload=link))
    elif t == "billing.payment.failed" and d.get("recurring"):
        session.add(Notification(user_id=user, kind="subscription_renew_failed", title="Не удалось продлить подписку",
                                 body=f"{d.get('error') or 'Оплата не прошла'}. Попробуем ещё раз; можно оплатить вручную.",
                                 payload=link))


def _offer_notification(session: AsyncSession, t: str, d: dict) -> None:
    """Наборы в группы и пробные занятия."""
    add = session.add
    if t.startswith("marketplace.trial."):
        if t == "marketplace.trial.followup_created":
            add(Notification(user_id=UUID(d["student_id"]), kind="trial_followup", title="Как прошло пробное занятие?",
                             body=f"Оставьте отзыв и напишите, будете ли заниматься с педагогом {d.get('tutor_name') or ''} дальше."
                             if d.get("tutor_name") else "Оставьте отзыв и напишите, будете ли заниматься с педагогом дальше.",
                             payload={"href": "/dashboard"}))
        elif t == "marketplace.trial.answered":
            yes = d["decision"] == "continue"
            add(Notification(user_id=UUID(d["tutor_id"]), kind="trial_answered",
                             title=f"{d['student_name']} {'хочет продолжить занятия' if yes else 'не будет продолжать'} после пробного",
                             body=d.get("comment") or "", payload={"href": "/dashboard/students"}))
        return
    tutor = UUID(d["tutor_id"])
    offer = {"offer_id": d["offer_id"], "href": f"/groups/{d['offer_id']}"}
    manage = {"offer_id": d["offer_id"], "href": "/dashboard/offers"}
    students = [UUID(s) for s in d.get("student_ids", [])]
    title = f"«{d['title']}»"
    if t == "marketplace.group_offer.joined":
        text = "В группе появился новый ученик" if d.get("started") else f"Записались {d['count']} из {d['max_students']} (минимум {d['min_students']})"
        add(Notification(user_id=tutor, kind="offer_joined", title=f"{d['student_name']} записывается в группу {title}", body=text,
                         payload=manage))
    elif t == "marketplace.group_offer.min_reached":
        add(Notification(user_id=tutor, kind="offer_min_reached", title=f"Набор в группу {title}: минимум набран",
                         body="Можно запускать группу — ученики привяжутся к вам, занятия поставите в расписание.", payload=manage))
    elif t == "marketplace.group_offer.started":
        for sid in students:
            add(Notification(user_id=sid, kind="offer_started", title=f"Группа {title} стартует",
                             body="Педагог запустил группу — занятия появятся в расписании.", payload={"href": "/dashboard/schedule"}))
    elif t == "marketplace.group_offer.underfilled":
        add(Notification(user_id=tutor, kind="offer_underfilled", title=f"Недобор в группу {title}",
                         body=f"Срок набора прошёл: записались {d['count']} при минимуме {d['min_students']}. Продлите набор или отмените его.",
                         payload=manage))
        for sid in students:
            add(Notification(user_id=sid, kind="offer_underfilled", title=f"Группа {title} пока не набралась",
                             body="Педагог решит — продлить набор или отменить. Мы сообщим.", payload=offer))
    elif t == "marketplace.group_offer.extended":
        for sid in students:
            add(Notification(user_id=sid, kind="offer_extended", title=f"Набор в группу {title} продлён",
                             body="Ваше место сохранено.", payload=offer))
    elif t == "marketplace.group_offer.cancelled":
        for sid in students:
            add(Notification(user_id=sid, kind="offer_cancelled", title=f"Набор в группу {title} отменён",
                             body="Педагог отменил набор. Посмотрите другие группы.", payload={"href": "/groups"}))
