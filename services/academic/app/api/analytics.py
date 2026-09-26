"""Аналитика и отчёты педагога (ТЗ, раздел 8). Средний балл и посещаемость — всем; динамика, сравнение с классом,
тепловая карта пропусков, сводная ведомость и выгрузка в Excel/PDF — на тарифе «Базовый»."""

from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import quote
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError
from testmatica_common.plans import BASIC, FREE

from .. import analytics, people, reports, stats
from ..deps import auth, classroom, db, plans
from ..models import Attendance, Grade
from ..schemas import GroupReport, StudentReport, Summary
from .journal import type_names

router = APIRouter(prefix="/analytics", tags=["analytics"])
teacher = auth.require(ROLE_TEACHER)

MAX_DAYS = 366


class Period:
    """Период отчёта в часовом поясе педагога: с начала первого дня до конца последнего."""

    def __init__(
        self,
        start: date = Query(alias="from"),
        end: date = Query(alias="to"),
        tz: str = Query("Europe/Moscow", max_length=64),
        subject: str | None = Query(None, max_length=80),
    ) -> None:
        if end < start or (end - start).days > MAX_DAYS:
            raise ApiError(422, "invalid_range", "Период — не больше года")
        try:
            self.zone = ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            raise ApiError(422, "invalid_timezone", "Неизвестный часовой пояс") from None
        self.start, self.end, self.subject = start, end, subject
        self.since = datetime.combine(start, time.min, self.zone).astimezone(UTC)
        self.until = datetime.combine(end + timedelta(days=1), time.min, self.zone).astimezone(UTC)

    @property
    def dates(self) -> tuple[date, date]:
        return self.start, self.end


async def _extended(teacher_id: UUID) -> bool:
    return await plans.of(teacher_id, fallback=FREE) == BASIC


async def _require_extended(teacher_id: UUID) -> None:
    if not await _extended(teacher_id):
        raise ApiError(403, "plan_required", "Сводная ведомость и выгрузка — на тарифе «Базовый»")


async def _load(session: AsyncSession, teacher_id: UUID, p: Period, *conds) -> tuple[list[Grade], list[Attendance]]:
    g = select(Grade).where(Grade.teacher_id == teacher_id, Grade.lesson_starts_at >= p.since, Grade.lesson_starts_at < p.until,
                            *[c(Grade) for c in conds])
    a = select(Attendance).where(Attendance.teacher_id == teacher_id, Attendance.lesson_starts_at >= p.since,
                                 Attendance.lesson_starts_at < p.until, *[c(Attendance) for c in conds])
    if p.subject:
        g, a = g.where(Grade.subject == p.subject), a.where(Attendance.subject == p.subject)
    return list((await session.execute(g)).scalars()), list((await session.execute(a)).scalars())


def _file(content: bytes, fmt: str, name: str) -> Response:
    media = "application/pdf" if fmt == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(content, media_type=media, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(f'{name}.{fmt}')}"})


# ---------- класс / группа ----------


async def _group_report(session: AsyncSession, group_id: UUID, principal: Principal, p: Period, extended: bool) -> GroupReport:
    group = await classroom.get(f"/internal/groups/{group_id}", params={"teacher_id": str(principal.user_id)})
    grades, marks = await _load(session, principal.user_id, p, lambda m: m.group_id == group_id)
    current = {UUID(s) for s in group["member_ids"]}
    names = await people.names(session, current | {g.student_id for g in grades} | {a.student_id for a in marks})
    return analytics.group_report(group["title"], p.subject, p.dates, grades, marks, current, names, p.zone, extended)


@router.get("/groups/{group_id}", response_model=GroupReport)
async def group_report(
    group_id: UUID, p: Period = Depends(), principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> GroupReport:
    return await _group_report(session, group_id, principal, p, await _extended(principal.user_id))


@router.get("/groups/{group_id}/export")
async def group_export(
    group_id: UUID, format: str = Query(pattern="^(xlsx|pdf)$"), p: Period = Depends(), principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> Response:
    await _require_extended(principal.user_id)
    r = await _group_report(session, group_id, principal, p, True)
    content = reports.group_pdf(r) if format == "pdf" else reports.group_xlsx(r)
    return _file(content, format, f"Аналитика {r.title} {p.start:%d.%m}-{p.end:%d.%m.%Y}")


# ---------- ученик ----------


async def _student_report(session: AsyncSession, student_id: UUID, principal: Principal, p: Period, extended: bool) -> StudentReport:
    # Свой ученик (в том числе бывший) — иначе 404 от classroom.
    await classroom.get("/internal/links", params={"teacher_id": str(principal.user_id), "student_id": str(student_id)})
    grades, marks = await _load(session, principal.user_id, p, lambda m: m.student_id == student_id)
    group_ids = {g.group_id for g in grades if g.group_id} | {a.group_id for a in marks if a.group_id}
    class_grades = []
    if extended and group_ids:
        class_grades, _ = await _load(session, principal.user_id, p, lambda m: m.group_id.in_(group_ids))
    name = (await people.names(session, [student_id])).get(student_id, people.UNKNOWN_NAME)
    return analytics.student_report(name, p.dates, grades, marks, class_grades, await type_names(session), p.zone, extended)


@router.get("/students/{student_id}", response_model=StudentReport)
async def student_report(
    student_id: UUID, p: Period = Depends(), principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> StudentReport:
    return await _student_report(session, student_id, principal, p, await _extended(principal.user_id))


@router.get("/students/{student_id}/export")
async def student_export(
    student_id: UUID, format: str = Query(pattern="^(xlsx|pdf)$"), p: Period = Depends(), principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> Response:
    await _require_extended(principal.user_id)
    r = await _student_report(session, student_id, principal, p, True)
    content = reports.student_pdf(r) if format == "pdf" else reports.student_xlsx(r)
    return _file(content, format, f"Аналитика {r.full_name} {p.start:%d.%m}-{p.end:%d.%m.%Y}")


# ---------- сводная ведомость ----------


async def _summary(session: AsyncSession, principal: Principal, p: Period) -> Summary:
    groups = await classroom.get(f"/internal/teachers/{principal.user_id}/groups", params={"archived": "true"})
    grades, marks = await _load(session, principal.user_id, p)
    rows = []
    for g in groups:
        gid = UUID(g["id"])
        gg, ga = [x for x in grades if x.group_id == gid], [x for x in marks if x.group_id == gid]
        if g["archived"] and not gg and not ga:
            continue  # архивные — только если за период что-то было
        title = g["title"] + (" (архив)" if g["archived"] else "")
        rows.append(analytics.summary_line(gid, title, {UUID(s) for s in g["member_ids"]}, gg, ga))
    solo_g, solo_a = [x for x in grades if x.group_id is None], [x for x in marks if x.group_id is None]
    if solo_g or solo_a:
        rows.append(analytics.summary_line(None, "Индивидуальные занятия", set(), solo_g, solo_a))
    return Summary(period_from=p.start, period_to=p.end, rows=rows, total=stats.compute(grades, marks))


@router.get("/summary", response_model=Summary)
async def summary(p: Period = Depends(), principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> Summary:
    """Сводная ведомость по всем классам и группам педагога."""
    await _require_extended(principal.user_id)
    return await _summary(session, principal, p)


@router.get("/summary/export")
async def summary_export(
    format: str = Query(pattern="^(xlsx|pdf)$"), p: Period = Depends(), principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> Response:
    await _require_extended(principal.user_id)
    r = await _summary(session, principal, p)
    content = reports.summary_pdf(r) if format == "pdf" else reports.summary_xlsx(r)
    return _file(content, format, f"Сводная ведомость {p.start:%d.%m}-{p.end:%d.%m.%Y}")
