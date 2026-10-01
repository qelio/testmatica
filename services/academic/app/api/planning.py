"""Учебное планирование (КТП): шаблоны планов и КТП конкретного класса, группы или ученика с датами."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_ADMIN, ROLE_MODERATOR, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import people
from ..deps import auth, classroom, db, outbox, schedule
from ..models import (
    TEMPLATE_PENDING,
    TEMPLATE_PRIVATE,
    TEMPLATE_PUBLISHED,
    TEMPLATE_REJECTED,
    TEMPLATE_REMOVED,
    Plan,
    PlanLesson,
    PlanTemplate,
    TemplateLesson,
)
from ..schemas import (
    DistributeIn,
    DistributeOut,
    LessonIn,
    LessonKtp,
    PlanCreate,
    PlanLessonOut,
    PlanLessonUpdate,
    PlanOut,
    PlanSummary,
    PlanUpdate,
    Slot,
    TemplateIn,
    TemplateLessonOut,
    TemplateOut,
    TemplateSummary,
)

router = APIRouter(tags=["planning"])
author = auth.require(ROLE_TEACHER, ROLE_MODERATOR)
teacher = auth.require(ROLE_TEACHER)

# Сколько вперёд смотреть расписание при раскладке уроков по занятиям.
HORIZON = timedelta(days=400)


def _is_staff(p: Principal) -> bool:
    return p.has_any(ROLE_MODERATOR)


def _lesson_fields(lesson: LessonIn) -> dict:
    return {
        "topic": lesson.topic,
        "goals": lesson.goals,
        "class_items": [i.model_dump(mode="json") for i in lesson.class_items],
        "home_items": [i.model_dump(mode="json") for i in lesson.home_items],
        "exam_item_ids": list(dict.fromkeys(lesson.exam_item_ids)),
    }


def _copy_fields(src) -> dict:
    return {"topic": src.topic, "goals": src.goals, "class_items": src.class_items, "home_items": src.home_items,
            "exam_item_ids": list(src.exam_item_ids or [])}


# ---------- шаблоны ----------


async def _template_summaries(session: AsyncSession, rows: list[PlanTemplate]) -> list[TemplateSummary]:
    names = await people.names(session, {t.owner_id for t in rows})
    return [
        TemplateSummary(id=t.id, title=t.title, subject=t.subject, level=t.level, status=t.status, owner_id=t.owner_id,
                        author_name=names.get(t.owner_id, people.UNKNOWN_NAME), lessons_count=len(t.lessons), updated_at=t.updated_at)
        for t in rows
    ]


async def _template_out(session: AsyncSession, t: PlanTemplate, p: Principal) -> TemplateOut:
    await session.refresh(t)
    [summary] = await _template_summaries(session, [t])
    mine = t.owner_id == p.user_id
    return TemplateOut(
        **summary.model_dump(), description=t.description, review_comment=t.review_comment if mine or _is_staff(p) else None,
        based_on_id=t.based_on_id, can_edit=mine and (t.status in (TEMPLATE_PRIVATE, TEMPLATE_REJECTED) or (t.status == TEMPLATE_PUBLISHED and _is_staff(p))),
        lessons=[TemplateLessonOut(id=x.id, **_copy_fields(x)) for x in t.lessons],
    )


async def _visible_template(session: AsyncSession, template_id: UUID, p: Principal, lock: bool = False) -> PlanTemplate:
    t = await session.get(PlanTemplate, template_id, with_for_update=lock)
    if t is None or not (t.owner_id == p.user_id or t.status == TEMPLATE_PUBLISHED or _is_staff(p)):
        raise ApiError(404, "template_not_found", "Шаблон не найден")
    return t


async def _usable_template(session: AsyncSession, template_id: UUID, p: Principal) -> PlanTemplate:
    """Шаблон, на основе которого можно сделать копию или КТП: снятый администратором — нельзя."""
    t = await _visible_template(session, template_id, p)
    if t.status == TEMPLATE_REMOVED and not _is_staff(p):
        raise ApiError(409, "template_removed", "Шаблон снят с платформы администратором")
    return t


async def _own_template(session: AsyncSession, template_id: UUID, p: Principal) -> PlanTemplate:
    t = await session.get(PlanTemplate, template_id, with_for_update=True)
    if t is None or t.owner_id != p.user_id:
        raise ApiError(404, "template_not_found", "Шаблон не найден")
    return t


@router.get("/plan-templates", response_model=list[TemplateSummary])
async def templates(
    scope: str = Query("mine", pattern="^(mine|public)$"),
    q: str | None = Query(None, max_length=100),
    subject: str | None = Query(None, max_length=80),
    principal: Principal = Depends(author),
    session: AsyncSession = Depends(db.session),
) -> list[TemplateSummary]:
    """Мои шаблоны (в любом статусе) или публичная библиотека КТП."""
    query = select(PlanTemplate).where(
        PlanTemplate.owner_id == principal.user_id if scope == "mine" else PlanTemplate.status == TEMPLATE_PUBLISHED
    )
    if q:
        query = query.where(or_(PlanTemplate.title.ilike(f"%{q.strip()}%"), PlanTemplate.level.ilike(f"%{q.strip()}%")))
    if subject:
        query = query.where(PlanTemplate.subject == subject)
    rows = (await session.execute(query.order_by(PlanTemplate.updated_at.desc()).limit(100))).scalars().all()
    return await _template_summaries(session, list(rows))


def _apply_template(t: PlanTemplate, body: TemplateIn) -> None:
    t.title, t.subject, t.level, t.description = body.title, body.subject, body.level, body.description
    t.lessons = [TemplateLesson(position=i, **_lesson_fields(x)) for i, x in enumerate(body.lessons)]
    t.updated_at = datetime.now(UTC)


@router.post("/plan-templates", response_model=TemplateOut, status_code=201)
async def create_template(body: TemplateIn, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> TemplateOut:
    t = PlanTemplate(owner_id=principal.user_id)
    _apply_template(t, body)
    session.add(t)
    await session.commit()
    return await _template_out(session, t, principal)


@router.get("/plan-templates/{template_id}", response_model=TemplateOut)
async def get_template(template_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> TemplateOut:
    return await _template_out(session, await _visible_template(session, template_id, principal), principal)


@router.put("/plan-templates/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: UUID, body: TemplateIn, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)
) -> TemplateOut:
    t = await _own_template(session, template_id, principal)
    if t.status == TEMPLATE_PENDING:
        raise ApiError(409, "template_pending", "Шаблон на проверке — отзовите его, чтобы изменить")
    if t.status == TEMPLATE_PUBLISHED and not _is_staff(principal):
        raise ApiError(409, "template_published", "Шаблон опубликован — снимите с публикации, чтобы изменить")
    if t.status == TEMPLATE_REMOVED:
        raise ApiError(409, "template_removed", "Шаблон снят с платформы администратором")
    _apply_template(t, body)
    await session.commit()
    return await _template_out(session, t, principal)


@router.delete("/plan-templates/{template_id}", status_code=204)
async def delete_template(template_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> None:
    t = await _own_template(session, template_id, principal)
    if t.status in (TEMPLATE_PENDING, TEMPLATE_PUBLISHED):
        await outbox.event(session, "academic.plan_template.unpublished",
                           {"template_id": str(t.id), "title": t.title, "author_id": str(t.owner_id)}, actor_id=principal.user_id)
    await session.delete(t)
    await session.commit()


@router.post("/plan-templates/{template_id}/copy", response_model=TemplateOut, status_code=201)
async def copy_template(template_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> TemplateOut:
    """План на основе чужого: своя приватная копия, которую можно править."""
    src = await _usable_template(session, template_id, principal)
    t = PlanTemplate(owner_id=principal.user_id, title=src.title, subject=src.subject, level=src.level,
                     description=src.description, based_on_id=src.id,
                     lessons=[TemplateLesson(position=x.position, **_copy_fields(x)) for x in src.lessons])
    session.add(t)
    await session.commit()
    return await _template_out(session, t, principal)


@router.post("/plan-templates/{template_id}/submit", response_model=TemplateOut)
async def submit_template(template_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> TemplateOut:
    """В публичную библиотеку КТП — через модерацию; шаблоны модераторов (методистов) публикуются сразу."""
    t = await _own_template(session, template_id, principal)
    if t.status not in (TEMPLATE_PRIVATE, TEMPLATE_REJECTED):
        raise ApiError(409, "invalid_status", "Шаблон уже опубликован или на проверке")
    if not t.lessons:
        raise ApiError(422, "template_empty", "Добавьте в шаблон хотя бы один урок")
    data = {"template_id": str(t.id), "title": t.title, "author_id": str(t.owner_id), "lessons_count": len(t.lessons),
            "subject": t.subject}
    t.review_comment = None
    if _is_staff(principal):
        t.status, t.published_at = TEMPLATE_PUBLISHED, datetime.now(UTC)
        await outbox.event(session, "academic.plan_template.published", data, actor_id=principal.user_id)
    else:
        t.status = TEMPLATE_PENDING
        await outbox.event(session, "academic.plan_template.submitted", data, actor_id=principal.user_id)
    await session.commit()
    return await _template_out(session, t, principal)


@router.post("/plan-templates/{template_id}/unpublish", response_model=TemplateOut)
async def unpublish_template(template_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> TemplateOut:
    t = await session.get(PlanTemplate, template_id, with_for_update=True)
    if t is None or not (t.owner_id == principal.user_id or _is_staff(principal)):
        raise ApiError(404, "template_not_found", "Шаблон не найден")
    if t.status not in (TEMPLATE_PENDING, TEMPLATE_PUBLISHED):
        raise ApiError(409, "invalid_status", "Шаблон не опубликован")
    t.status = TEMPLATE_PRIVATE
    await outbox.event(session, "academic.plan_template.unpublished",
                       {"template_id": str(t.id), "title": t.title, "author_id": str(t.owner_id)}, actor_id=principal.user_id)
    await session.commit()
    return await _template_out(session, t, principal)


# ---------- КТП цели ----------


async def _target_title(p: Principal, target_type: str, target_id: UUID, session: AsyncSession) -> tuple[str, str | None]:
    """Проверить, что группа или ученик — свои. Возвращает название и предмет (для группы)."""
    if target_type == "group":
        group = await classroom.get(f"/internal/groups/{target_id}", params={"teacher_id": str(p.user_id)})
        return group["title"], group.get("subject")
    link = await classroom.get("/internal/links", params={"teacher_id": str(p.user_id), "student_id": str(target_id)})
    if not link["active"]:
        raise ApiError(404, "student_not_found", "Ученик не привязан к вам")
    return await people.name_of(session, target_id), None


async def _slots(p: Principal, plan: Plan, start: date | None) -> list[dict]:
    """Занятия цели в расписании от даты (включительно), без отменённых."""
    frm = datetime.combine(start or date.today(), time.min, tzinfo=UTC) - timedelta(days=1)
    params = {"teacher_id": str(p.user_id), "from": frm.isoformat(), "to": (frm + HORIZON).isoformat(),
              f"{plan.target_type}_id": str(plan.target_id)}
    lessons = await schedule.get("/internal/lessons", params=params)
    return [x for x in lessons if x["status"] == "scheduled"]


def _local_date(starts_at: str, tz: ZoneInfo) -> date:
    return datetime.fromisoformat(starts_at).astimezone(tz).date()


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Moscow")


def _distribute(plan: Plan, slots: list[dict], start: date, tz: ZoneInfo) -> DistributeOut:
    """Разложить непройденные уроки по занятиям подряд, начиная с даты. Пройденные и более ранние не трогаем.
    Если занятий не хватило — у оставшихся уроков дата и занятие сбрасываются."""
    free = [s for s in slots if _local_date(s["starts_at"], tz) >= start]
    taken = {
        x.schedule_lesson_id for x in plan.lessons
        if x.done or (x.planned_date is not None and x.planned_date < start)
    }
    free = [s for s in free if UUID(s["id"]) not in taken]
    todo = [x for x in plan.lessons if not x.done and not (x.planned_date is not None and x.planned_date < start)]
    for lesson, slot in zip(todo, free, strict=False):
        lesson.schedule_lesson_id = UUID(slot["id"])
        lesson.planned_date = _local_date(slot["starts_at"], tz)
    for lesson in todo[len(free):]:
        lesson.schedule_lesson_id, lesson.planned_date = None, None
    return DistributeOut(placed=min(len(todo), len(free)), left=max(0, len(todo) - len(free)))


def _lesson_out(x: PlanLesson) -> PlanLessonOut:
    return PlanLessonOut(id=x.id, position=x.position, planned_date=x.planned_date, schedule_lesson_id=x.schedule_lesson_id,
                         done=x.done, **_copy_fields(x))


async def _target_titles(session: AsyncSession, plans: list[Plan]) -> dict[UUID, str]:
    """Для плана ученика — его текущее имя из реплики («Фамилия Имя»), а не копия на момент создания плана."""
    names = await people.names(session, {x.target_id for x in plans if x.target_type == "student"})
    return {x.id: names.get(x.target_id, x.target_title) if x.target_type == "student" else x.target_title for x in plans}


async def _plan_out(session: AsyncSession, plan: Plan, p: Principal) -> PlanOut:
    await session.refresh(plan)
    slots = await _slots(p, plan, plan.start_date)
    titles = await _target_titles(session, [plan])
    return PlanOut(
        id=plan.id, title=plan.title, subject=plan.subject, target_type=plan.target_type, target_id=plan.target_id,
        target_title=titles[plan.id], template_id=plan.template_id, start_date=plan.start_date,
        lessons=[_lesson_out(x) for x in plan.lessons],
        slots=[Slot(id=s["id"], starts_at=s["starts_at"], topic=s["topic"]) for s in slots],
        updated_at=plan.updated_at,
    )


async def _own_plan(session: AsyncSession, plan_id: UUID, p: Principal) -> Plan:
    plan = await session.get(Plan, plan_id, with_for_update=True)
    if plan is None or plan.teacher_id != p.user_id:
        raise ApiError(404, "plan_not_found", "План не найден")
    return plan


@router.get("/plans", response_model=list[PlanSummary])
async def plans(
    target_id: UUID | None = None, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> list[PlanSummary]:
    query = select(Plan).where(Plan.teacher_id == principal.user_id)
    if target_id:
        query = query.where(Plan.target_id == target_id)
    rows = (await session.execute(query.order_by(Plan.updated_at.desc()))).scalars().all()
    titles = await _target_titles(session, list(rows))
    out = []
    for plan in rows:
        upcoming = next((x for x in plan.lessons if not x.done), None)
        out.append(PlanSummary(
            id=plan.id, title=plan.title, subject=plan.subject, target_type=plan.target_type, target_id=plan.target_id,
            target_title=titles[plan.id], lessons_count=len(plan.lessons), done_count=sum(x.done for x in plan.lessons),
            next_topic=upcoming.topic if upcoming else None, next_date=upcoming.planned_date if upcoming else None,
            updated_at=plan.updated_at,
        ))
    return out


@router.post("/plans", response_model=PlanOut, status_code=201)
async def create_plan(
    body: PlanCreate,
    tz: str = Query("Europe/Moscow", max_length=64),
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> PlanOut:
    """КТП для группы или ученика: пустой (с нуля, постепенно) или из шаблона — со своими датами."""
    target_title, group_subject = await _target_title(principal, body.target_type, body.target_id, session)
    template = await _usable_template(session, body.template_id, principal) if body.template_id else None
    plan = Plan(
        teacher_id=principal.user_id, target_type=body.target_type, target_id=body.target_id, target_title=target_title,
        title=body.title or (template.title if template else "КТП"),
        subject=body.subject or (template.subject if template else None) or group_subject,
        template_id=template.id if template else None, start_date=body.start_date,
        lessons=[PlanLesson(position=x.position, **_copy_fields(x)) for x in template.lessons] if template else [],
    )
    session.add(plan)
    await session.flush()
    if body.distribute and plan.lessons:
        start = body.start_date or date.today()
        _distribute(plan, await _slots(principal, plan, start), start, _zone(tz))
    await session.commit()
    return await _plan_out(session, plan, principal)


@router.get("/plans/{plan_id}", response_model=PlanOut)
async def get_plan(plan_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> PlanOut:
    plan = await session.get(Plan, plan_id)
    if plan is None or plan.teacher_id != principal.user_id:
        raise ApiError(404, "plan_not_found", "План не найден")
    return await _plan_out(session, plan, principal)


@router.patch("/plans/{plan_id}", response_model=PlanOut)
async def update_plan(
    plan_id: UUID, body: PlanUpdate, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> PlanOut:
    plan = await _own_plan(session, plan_id, principal)
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "title" and not value:
            continue
        setattr(plan, field, value)
    plan.updated_at = datetime.now(UTC)
    await session.commit()
    return await _plan_out(session, plan, principal)


@router.delete("/plans/{plan_id}", status_code=204)
async def delete_plan(plan_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> None:
    await session.delete(await _own_plan(session, plan_id, principal))
    await session.commit()


@router.post("/plans/{plan_id}/distribute", response_model=DistributeOut)
async def distribute(
    plan_id: UUID, body: DistributeIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> DistributeOut:
    """Проставить даты: непройденные уроки по порядку — на занятия расписания начиная с даты."""
    plan = await _own_plan(session, plan_id, principal)
    start = body.from_date or plan.start_date or date.today()
    result = _distribute(plan, await _slots(principal, plan, start), start, _zone(body.tz))
    plan.updated_at = datetime.now(UTC)
    await session.commit()
    return result


@router.post("/plans/{plan_id}/lessons", response_model=PlanLessonOut, status_code=201)
async def add_lesson(
    plan_id: UUID,
    body: LessonIn,
    after: UUID | None = Query(None, description="Вставить после этого урока; по умолчанию — в конец"),
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> PlanLessonOut:
    """Постепенное заполнение: урок за уроком по мере работы."""
    plan = await _own_plan(session, plan_id, principal)
    ordered = list(plan.lessons)
    index = next((i + 1 for i, x in enumerate(ordered) if x.id == after), len(ordered))
    lesson = PlanLesson(plan_id=plan.id, **_lesson_fields(body))
    ordered.insert(index, lesson)
    for i, x in enumerate(ordered):
        x.position = i
    plan.lessons = ordered
    plan.updated_at = datetime.now(UTC)
    await session.commit()
    return _lesson_out(lesson)


async def _check_slot(p: Principal, plan: Plan, lesson_id: UUID) -> dict:
    """Занятие для урока КТП: своё и той же группы или того же ученика."""
    found = await schedule.get(f"/internal/lessons/{lesson_id}", params={"teacher_id": str(p.user_id)})
    key = "group_id" if plan.target_type == "group" else "student_id"
    if found.get(key) != str(plan.target_id) or found["status"] != "scheduled":
        raise ApiError(422, "slot_mismatch", "Это занятие не относится к классу или ученику плана")
    return found


@router.patch("/plans/{plan_id}/lessons/{lesson_id}", response_model=PlanLessonOut)
async def update_lesson(
    plan_id: UUID,
    lesson_id: UUID,
    body: PlanLessonUpdate,
    tz: str = Query("Europe/Moscow", max_length=64),
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> PlanLessonOut:
    """Правка урока КТП: тема, результаты, материалы, дата, занятие в расписании, «пройден»."""
    plan = await _own_plan(session, plan_id, principal)
    lesson = next((x for x in plan.lessons if x.id == lesson_id), None)
    if lesson is None:
        raise ApiError(404, "lesson_not_found", "Урок не найден")
    data = body.model_dump(exclude_unset=True, mode="json")
    if "schedule_lesson_id" in data:
        if body.schedule_lesson_id is not None:
            slot = await _check_slot(principal, plan, body.schedule_lesson_id)
            lesson.planned_date = _local_date(slot["starts_at"], _zone(tz))
        lesson.schedule_lesson_id = body.schedule_lesson_id
        data.pop("schedule_lesson_id")
        data.pop("planned_date", None)
    elif "planned_date" in data:
        # Дата вручную — без привязки к конкретному занятию.
        lesson.planned_date, lesson.schedule_lesson_id = body.planned_date, None
        data.pop("planned_date")
    for field in ("topic", "goals", "class_items", "home_items", "exam_item_ids", "done"):
        if field in data and data[field] is not None:
            setattr(lesson, field, getattr(body, field) if field == "exam_item_ids" else data[field])
    plan.updated_at = datetime.now(UTC)
    await session.commit()
    return _lesson_out(lesson)


@router.delete("/plans/{plan_id}/lessons/{lesson_id}", status_code=204)
async def delete_lesson(plan_id: UUID, lesson_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> None:
    plan = await _own_plan(session, plan_id, principal)
    rest = [x for x in plan.lessons if x.id != lesson_id]
    if len(rest) == len(plan.lessons):
        raise ApiError(404, "lesson_not_found", "Урок не найден")
    for i, x in enumerate(rest):
        x.position = i
    plan.lessons = rest
    plan.updated_at = datetime.now(UTC)
    await session.commit()


@router.post("/plans/{plan_id}/lessons/{lesson_id}/move", response_model=PlanOut)
async def move_lesson(
    plan_id: UUID, lesson_id: UUID, to: int = Query(ge=0), principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> PlanOut:
    """Переставить урок. Даты остаются у мест: при желании — «Проставить даты» заново."""
    plan = await _own_plan(session, plan_id, principal)
    ordered = list(plan.lessons)
    lesson = next((x for x in ordered if x.id == lesson_id), None)
    if lesson is None:
        raise ApiError(404, "lesson_not_found", "Урок не найден")
    ordered.remove(lesson)
    ordered.insert(min(to, len(ordered)), lesson)
    for i, x in enumerate(ordered):
        x.position = i
    plan.updated_at = datetime.now(UTC)
    await session.commit()
    return await _plan_out(session, plan, principal)


@router.post("/plans/{plan_id}/save-as-template", response_model=TemplateOut, status_code=201)
async def save_as_template(plan_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> TemplateOut:
    """План, составленный постепенно, — в шаблон: привязать к другим классам или опубликовать."""
    plan = await _own_plan(session, plan_id, principal)
    if not plan.lessons:
        raise ApiError(422, "plan_empty", "В плане нет уроков")
    t = PlanTemplate(owner_id=principal.user_id, title=plan.title, subject=plan.subject, based_on_id=plan.template_id,
                     lessons=[TemplateLesson(position=x.position, **_copy_fields(x)) for x in plan.lessons])
    session.add(t)
    await session.commit()
    return await _template_out(session, t, principal)


@router.get("/ktp/by-lesson/{schedule_lesson_id}", response_model=list[LessonKtp])
async def by_schedule_lesson(
    schedule_lesson_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> list[LessonKtp]:
    """Уроки КТП на занятии — для карточки занятия в расписании."""
    rows = await session.execute(
        select(PlanLesson, Plan.id, Plan.title).join(Plan, Plan.id == PlanLesson.plan_id)
        .where(Plan.teacher_id == principal.user_id, PlanLesson.schedule_lesson_id == schedule_lesson_id)
        .order_by(Plan.title, PlanLesson.position)
    )
    return [LessonKtp(plan_id=pid, plan_title=title, lesson=_lesson_out(x)) for x, pid, title in rows]


# ---------- администратор ----------


class RemoveIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/admin/plan-templates/{template_id}/remove", response_model=TemplateOut)
async def admin_remove_template(
    template_id: UUID, body: RemoveIn, principal: Principal = Depends(auth.require(ROLE_ADMIN)), session: AsyncSession = Depends(db.session)
) -> TemplateOut:
    """Администратор снимает любой шаблон с платформы без очереди модерации. КТП, уже сделанные по нему, остаются."""
    t = await session.get(PlanTemplate, template_id, with_for_update=True)
    if t is None:
        raise ApiError(404, "template_not_found", "Шаблон не найден")
    if t.status != TEMPLATE_REMOVED:
        t.removed_from = t.status
        t.status, t.review_comment = TEMPLATE_REMOVED, body.reason.strip()
        await outbox.event(session, "academic.plan_template.removed", {
            "template_id": str(t.id), "title": t.title, "author_id": str(t.owner_id), "reason": t.review_comment,
        }, actor_id=principal.user_id)
        await session.commit()
    return await _template_out(session, t, principal)


@router.post("/admin/plan-templates/{template_id}/restore", response_model=TemplateOut)
async def admin_restore_template(
    template_id: UUID, principal: Principal = Depends(auth.require(ROLE_ADMIN)), session: AsyncSession = Depends(db.session)
) -> TemplateOut:
    t = await session.get(PlanTemplate, template_id, with_for_update=True)
    if t is None or t.status != TEMPLATE_REMOVED:
        raise ApiError(409, "not_removed", "Шаблон не снят с платформы")
    # Прежний статус; бывший на проверке — в приватные (заявку из очереди уже сняли).
    was = t.removed_from
    t.status = was if was in (TEMPLATE_PUBLISHED, TEMPLATE_PRIVATE, TEMPLATE_REJECTED) else TEMPLATE_PRIVATE
    t.review_comment, t.removed_from = None, None
    await outbox.event(session, "academic.plan_template.restored",
                       {"template_id": str(t.id), "title": t.title, "author_id": str(t.owner_id)}, actor_id=principal.user_id)
    await session.commit()
    return await _template_out(session, t, principal)
