"""Чтение библиотеки: каталог, курс, модуль. Публичное доступно без входа."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError

from .. import access, views
from ..deps import auth, db
from ..models import PENDING, PUBLISHED, Node, RelLink
from ..schemas import CourseOut, CourseSummary, ModuleContent

router = APIRouter(tags=["catalog"])


@router.get("/catalog", response_model=list[CourseSummary])
async def catalog(
    subject_id: UUID | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(db.session),
) -> list[CourseSummary]:
    """Публичная библиотека: опубликованные курсы. Доступна и без регистрации."""
    query = select(Node).where(Node.kind == "course", Node.status == PUBLISHED)
    if subject_id:
        query = query.where(Node.subject_id == subject_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Node.title.ilike(like), Node.description.ilike(like)))
    courses = (await session.execute(query.order_by(Node.published_at.desc()).limit(limit).offset(offset))).scalars().all()
    return await views.summaries(session, courses)


@router.get("/my/courses", response_model=list[CourseSummary])
async def my_courses(
    principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> list[CourseSummary]:
    """Моя библиотека: все курсы автора в любом статусе."""
    rows = await session.execute(
        select(Node).where(Node.kind == "course", Node.owner_id == principal.user_id, Node.revision_of.is_(None))
        .order_by(Node.updated_at.desc())
    )
    return await views.summaries(session, rows.scalars().all())


@router.get("/shared/courses", response_model=list[CourseSummary])
async def shared_courses(
    principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> list[CourseSummary]:
    """Для ученика: приватные библиотеки его педагогов."""
    teachers = select(RelLink.teacher_id).where(RelLink.student_id == principal.user_id)
    rows = await session.execute(
        select(Node).where(Node.kind == "course", Node.owner_id.in_(teachers), Node.revision_of.is_(None))
        .order_by(Node.updated_at.desc())
    )
    return await views.summaries(session, rows.scalars().all())


@router.get("/moderation/courses/{course_id}", response_model=CourseOut)
async def course_for_review(
    course_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> CourseOut:
    """То же, что /courses/{id}, но явно для модератора (курс на проверке)."""
    if not access.is_staff(principal):
        raise ApiError(403, "forbidden", "Только для модераторов")
    node, course = await access.load_node(session, course_id)
    if node.kind != "course" or course.status != PENDING:
        raise ApiError(404, "not_found", "Курс не найден среди ожидающих проверки")
    return await views.course_tree(session, course, principal)


@router.get("/courses/{course_id}", response_model=CourseOut)
async def course(
    course_id: UUID,
    principal: Principal | None = Depends(auth.optional),
    session: AsyncSession = Depends(db.session),
) -> CourseOut:
    node, course = await access.readable_node(session, course_id, principal)
    if node.kind != "course":
        raise ApiError(404, "not_found", "Курс не найден")
    return await views.course_tree(session, course, principal)


@router.get("/modules/{module_id}", response_model=ModuleContent)
async def module(
    module_id: UUID,
    principal: Principal | None = Depends(auth.optional),
    session: AsyncSession = Depends(db.session),
) -> ModuleContent:
    node, course = await access.readable_node(session, module_id, principal)
    if node.kind != "module":
        raise ApiError(404, "not_found", "Модуль не найден")
    return await views.module_content(session, node, course, principal)
