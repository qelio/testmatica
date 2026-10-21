"""Классный журнал педагога: «ученики × занятия», оценки и посещаемость."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import people, stats
from ..deps import auth, classroom, db, outbox, schedule
from ..models import Attendance, Grade, GradeType, Plan, PlanLesson
from ..schemas import (
    AttendanceOut,
    AttendanceSet,
    GradeCreate,
    GradeOut,
    GradeUpdate,
    Journal,
    JournalLesson,
    JournalStudent,
    JournalWork,
)

router = APIRouter(tags=["journal"])
teacher = auth.require(ROLE_TEACHER)

MAX_RANGE = timedelta(days=190)  # примерно полугодие


def grade_out(
    g: Grade, type_names: dict[UUID, str], viewer: UUID | None = None, names: dict[UUID, str] | None = None, edit_all: bool = False
) -> GradeOut:
    """viewer — кто смотрит журнал: чужие оценки (коллеги) помечаются own=False и подписываются его именем;
    edit_all — у смотрящего право менять все оценки класса (владелец или «правка всех оценок», решение №61)."""
    own = viewer is None or g.teacher_id == viewer
    return GradeOut(
        teacher_id=g.teacher_id,
        teacher_name=names.get(g.teacher_id) if names else None,
        own=own,
        can_edit=own or edit_all,
        id=g.id,
        lesson_id=g.lesson_id,
        work_id=g.source_ref if g.lesson_id is None else None,
        title=g.title,
        student_id=g.student_id,
        value=g.value,
        grade_type_id=g.grade_type_id,
        grade_type=type_names.get(g.grade_type_id, ""),
        comment=g.comment,
        source=g.source,
        lesson_starts_at=g.lesson_starts_at,
        created_at=g.created_at,
    )


async def type_names(session: AsyncSession) -> dict[UUID, str]:
    return dict((await session.execute(select(GradeType.id, GradeType.name))).all())


# ---------- журнал ----------


NO_SUBJECT = ""  # значение параметра subject для журнала «Без предмета»


def _subjects(found: set[str | None], main: str | None) -> list[str | None]:
    """Журналы по предметам: предмет класса — первым, дальше по алфавиту, «Без предмета» — последним."""
    named = sorted({x for x in found if x and x != main})
    out = ([main] if main else []) + named
    return out + [None] if None in found or not out else out


@router.get("/journal", response_model=Journal)
async def journal(
    group_id: UUID | None = None,
    student_id: UUID | None = None,
    start: datetime = Query(alias="from"),
    end: datetime = Query(alias="to"),
    subject: str | None = Query(None, description="Журнал предмета; пустая строка — «Без предмета», не указан — первый"),
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> Journal:
    """Журнал класса (группы) или ученика по предмету (решение №59). Журнал класса — общий для педагогов, с которыми
    им поделились: видны занятия и оценки всех, менять можно только свои."""
    if (group_id is None) == (student_id is None):
        raise ApiError(422, "invalid_target", "Выберите группу или ученика")
    if end <= start or end - start > MAX_RANGE:
        raise ApiError(422, "invalid_range", "Период — не больше полугода")

    me = principal.user_id
    target = {"group_id": str(group_id)} if group_id else {"student_id": str(student_id)}
    main_subject, edit_all = None, False
    if group_id:
        group = await classroom.get(f"/internal/groups/{group_id}", params={"teacher_id": str(me)})
        title, current, main_subject = group["title"], {UUID(s) for s in group["member_ids"]}, group.get("subject")
        edit_all = bool({"owner", "journal_all"} & set(group.get("permissions", [])))
    else:
        link = await classroom.get("/internal/links", params={"teacher_id": str(me), "student_id": str(student_id)})
        title, current = "", ({student_id} if link["active"] else set())

    lessons = await schedule.get(
        "/internal/lessons",
        params={"teacher_id": str(me), "from": start.isoformat(), "to": end.isoformat(), **target,
                **({"all_teachers": "true"} if group_id else {})},
    )
    lessons = [lesson for lesson in lessons if lesson["status"] == "scheduled"]
    lesson_ids = [UUID(lesson["id"]) for lesson in lessons]

    grades = list(
        (await session.execute(select(Grade).where(Grade.lesson_id.in_(lesson_ids)).order_by(Grade.created_at)))
        .scalars()
        .all()
        if lesson_ids
        else []
    )
    # Оценки за работы без урока: у группы — работы группе (всех педагогов), у ученика — свои, выданные лично ему.
    work_filter = (Grade.group_id == group_id) if group_id else (
        (Grade.teacher_id == me) & (Grade.student_id == student_id) & Grade.group_id.is_(None))
    grades += (
        await session.execute(
            select(Grade)
            .where(Grade.lesson_id.is_(None), work_filter, Grade.lesson_starts_at >= start, Grade.lesson_starts_at < end)
            .order_by(Grade.created_at)
        )
    ).scalars().all()

    # Предмет журнала: занятия — по своему предмету, оценки за работы — по предмету теста.
    subjects = _subjects({lesson["subject"] or None for lesson in lessons} | {g.subject or None for g in grades if g.lesson_id is None},
                         main_subject)
    chosen = (subject or None) if subject is not None else subjects[0]
    if chosen not in subjects:
        subjects.append(chosen)
    lessons = [lesson for lesson in lessons if (lesson["subject"] or None) == chosen]
    lesson_ids = [UUID(lesson["id"]) for lesson in lessons]
    kept = set(lesson_ids)
    grades = [g for g in grades if (g.lesson_id in kept if g.lesson_id else (g.subject or None) == chosen)]

    work_grades = {g.source_ref: g for g in grades if g.lesson_id is None and g.source_ref}
    marks = (
        (await session.execute(select(Attendance).where(Attendance.lesson_id.in_(lesson_ids)))).scalars().all()
        if lesson_ids
        else []
    )

    # Строки: текущий состав + все, кто был на занятиях периода или имеет записи.
    student_ids = set(current)
    for lesson in lessons:
        student_ids.update(UUID(s) for s in lesson["participant_ids"])
    student_ids.update(g.student_id for g in grades)
    student_ids.update(a.student_id for a in marks)
    teacher_ids = {UUID(lesson["teacher_id"]) for lesson in lessons} | {g.teacher_id for g in grades}
    names = await people.names(session, student_ids | teacher_ids)
    if student_id and not title:
        title = names.get(student_id, people.UNKNOWN_NAME)
    works = [JournalWork(id=ref, title=g.title or "Работа", at=g.lesson_starts_at, own=g.teacher_id == me,
                         teacher_name=names.get(g.teacher_id, people.UNKNOWN_NAME)) for ref, g in work_grades.items()]

    by_student_grades: dict[UUID, list[Grade]] = defaultdict(list)
    by_student_marks: dict[UUID, list[Attendance]] = defaultdict(list)
    for g in grades:
        by_student_grades[g.student_id].append(g)
    for a in marks:
        by_student_marks[a.student_id].append(a)

    now = datetime.now(UTC)
    types = await type_names(session)
    rows = [
        JournalStudent(
            id=sid,
            full_name=names.get(sid, people.UNKNOWN_NAME),
            current=sid in current,
            stats=stats.compute(by_student_grades[sid], by_student_marks[sid]),
        )
        for sid in student_ids
    ]
    rows.sort(key=lambda r: (not r.current, r.full_name))
    # Темы КТП у занятий — своих планов педагога.
    ktp: dict[UUID, list[str]] = defaultdict(list)
    if lesson_ids:
        linked = await session.execute(
            select(PlanLesson.schedule_lesson_id, PlanLesson.topic).join(Plan, Plan.id == PlanLesson.plan_id)
            .where(Plan.teacher_id == me, PlanLesson.schedule_lesson_id.in_(lesson_ids))
            .order_by(PlanLesson.position)
        )
        for lid, topic in linked:
            ktp[lid].append(topic)

    return Journal(
        title=title,
        subject=chosen,
        subjects=subjects,
        lessons=[
            JournalLesson(
                id=lesson["id"],
                starts_at=lesson["starts_at"],
                subject=lesson["subject"],
                topic=lesson["topic"],
                started=datetime.fromisoformat(lesson["starts_at"]) <= now,
                ktp=ktp.get(UUID(lesson["id"]), []),
                own=UUID(lesson["teacher_id"]) == me,
                teacher_name=names.get(UUID(lesson["teacher_id"]), people.UNKNOWN_NAME),
            )
            for lesson in lessons
        ],
        works=sorted(works, key=lambda w: w.at),
        students=rows,
        grades=[grade_out(g, types, me, names, edit_all) for g in grades],
        attendance=[AttendanceOut(lesson_id=a.lesson_id, student_id=a.student_id, status=a.status) for a in marks],
        stats=stats.compute(grades, marks),
    )


# ---------- проверка занятия ----------


async def _lesson(principal: Principal, lesson_id: UUID, student_id: UUID | None = None) -> dict:
    """Занятие педагога, уже начавшееся и не отменённое; ученик — его участник."""
    lesson = await schedule.get(f"/internal/lessons/{lesson_id}", params={"teacher_id": str(principal.user_id)})
    if lesson["status"] != "scheduled":
        raise ApiError(409, "lesson_cancelled", "Занятие отменено")
    if datetime.fromisoformat(lesson["starts_at"]) > datetime.now(UTC):
        raise ApiError(409, "lesson_not_started", "Занятие ещё не началось")
    if student_id is not None and str(student_id) not in lesson["participant_ids"]:
        raise ApiError(404, "student_not_found", "Этого ученика не было на занятии")
    return lesson


# ---------- посещаемость ----------


@router.put("/lessons/{lesson_id}/attendance/{student_id}", status_code=204)
async def set_attendance(
    lesson_id: UUID,
    student_id: UUID,
    body: AttendanceSet,
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> None:
    lesson = await _lesson(principal, lesson_id, student_id)
    if body.status is None:
        await session.execute(
            delete(Attendance).where(Attendance.lesson_id == lesson_id, Attendance.student_id == student_id)
        )
    else:
        await _upsert_attendance(session, lesson, [student_id], body.status, principal.user_id)
    await outbox.event(
        session,
        "academic.attendance.set",
        {"lesson_id": str(lesson_id), "student_id": str(student_id), "status": body.status},
        actor_id=principal.user_id,
    )
    await session.commit()


@router.post("/lessons/{lesson_id}/attendance/all-present", status_code=204)
async def all_present(
    lesson_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> None:
    """«Все присутствуют»: отметить тех, у кого отметки ещё нет."""
    lesson = await _lesson(principal, lesson_id)
    marked = set(
        (await session.execute(select(Attendance.student_id).where(Attendance.lesson_id == lesson_id))).scalars()
    )
    rest = [UUID(s) for s in lesson["participant_ids"] if UUID(s) not in marked]
    if rest:
        await _upsert_attendance(session, lesson, rest, "present", principal.user_id)
        await outbox.event(
            session,
            "academic.attendance.set",
            {"lesson_id": str(lesson_id), "student_ids": [str(s) for s in rest], "status": "present"},
            actor_id=principal.user_id,
        )
    await session.commit()


async def _upsert_attendance(session, lesson: dict, student_ids: list[UUID], status: str, teacher_id: UUID) -> None:
    rows = [
        {
            "lesson_id": UUID(lesson["id"]),
            "student_id": sid,
            "teacher_id": teacher_id,
            "lesson_starts_at": datetime.fromisoformat(lesson["starts_at"]),
            "group_id": UUID(lesson["group_id"]) if lesson["group_id"] else None,
            "subject": lesson["subject"],
            "status": status,
        }
        for sid in student_ids
    ]
    stmt = insert(Attendance).values(rows)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["lesson_id", "student_id"], set_={"status": stmt.excluded.status, "updated_at": datetime.now(UTC)}
        )
    )


# ---------- оценки ----------


async def _active_type(session: AsyncSession, type_id: UUID) -> GradeType:
    grade_type = await session.get(GradeType, type_id)
    if grade_type is None or not grade_type.is_active:
        raise ApiError(422, "invalid_grade_type", "Выберите тип оценки")
    return grade_type


async def _grade_event(session: AsyncSession, event: str, grade: Grade, grade_type: GradeType, actor: UUID) -> None:
    await outbox.event(
        session,
        event,
        {
            "grade_id": str(grade.id),
            "teacher_id": str(grade.teacher_id),
            "teacher_name": await people.name_of(session, grade.teacher_id),
            "student_id": str(grade.student_id),
            "lesson_id": str(grade.lesson_id) if grade.lesson_id else None,
            "title": grade.title,
            "lesson_starts_at": grade.lesson_starts_at.isoformat(),
            "subject": grade.subject,
            "value": grade.value,
            "grade_type": grade_type.name,
            "comment": grade.comment,
        },
        actor_id=actor,
    )


@router.post("/lessons/{lesson_id}/grades", response_model=GradeOut, status_code=201)
async def add_grade(
    lesson_id: UUID,
    body: GradeCreate,
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> GradeOut:
    lesson = await _lesson(principal, lesson_id, body.student_id)
    grade_type = await _active_type(session, body.grade_type_id)
    grade = Grade(
        teacher_id=principal.user_id,
        student_id=body.student_id,
        lesson_id=lesson_id,
        lesson_starts_at=datetime.fromisoformat(lesson["starts_at"]),
        group_id=UUID(lesson["group_id"]) if lesson["group_id"] else None,
        subject=lesson["subject"],
        value=body.value,
        grade_type_id=grade_type.id,
        comment=body.comment,
        source="manual",
    )
    session.add(grade)
    await session.flush()
    await _grade_event(session, "academic.grade.created", grade, grade_type, principal.user_id)
    await session.commit()
    return grade_out(grade, {grade_type.id: grade_type.name})


async def _own_grade(session: AsyncSession, grade_id: UUID, principal: Principal) -> Grade:
    """Своя оценка или оценка в журнале класса, где у педагога право менять все (владелец, «правка всех оценок»)."""
    grade = await session.get(Grade, grade_id, with_for_update=True)
    if grade is not None and grade.teacher_id != principal.user_id and grade.group_id:
        try:
            group = await classroom.get(f"/internal/groups/{grade.group_id}", params={"teacher_id": str(principal.user_id)})
        except ApiError as e:
            if e.status != 404:
                raise
        else:
            if {"owner", "journal_all"} & set(group.get("permissions", [])):
                return grade
    if grade is None or grade.teacher_id != principal.user_id:
        raise ApiError(404, "grade_not_found", "Оценка не найдена")
    return grade


@router.patch("/grades/{grade_id}", response_model=GradeOut)
async def update_grade(
    grade_id: UUID,
    body: GradeUpdate,
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> GradeOut:
    grade = await _own_grade(session, grade_id, principal)
    if body.grade_type_id is not None:
        grade.grade_type_id = (await _active_type(session, body.grade_type_id)).id
    if body.value is not None:
        grade.value = body.value
    if body.comment is not None:
        grade.comment = body.comment
    grade_type = await session.get(GradeType, grade.grade_type_id)
    await session.flush()
    await _grade_event(session, "academic.grade.updated", grade, grade_type, principal.user_id)
    await session.commit()
    await session.refresh(grade)
    return grade_out(grade, {grade_type.id: grade_type.name})


@router.delete("/grades/{grade_id}", status_code=204)
async def delete_grade(
    grade_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> None:
    grade = await _own_grade(session, grade_id, principal)
    grade_type = await session.get(GradeType, grade.grade_type_id)
    await _grade_event(session, "academic.grade.deleted", grade, grade_type, principal.user_id)
    await session.delete(grade)
    await session.commit()
