"""Сборка ответов: карточки курсов, дерево курса, содержимое модуля."""

from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError

from . import access
from .deps import media
from .models import Favorite, Material, MaterialProgress, Node, Person, Subject
from .schemas import (
    CourseOut,
    CourseSummary,
    FileInfo,
    MaterialBrief,
    MaterialOut,
    ModuleContent,
    ModuleOut,
    RevisionRef,
    SectionOut,
    SubjectOut,
)

UNKNOWN = "Автор"


async def names(session: AsyncSession, ids) -> dict[UUID, str]:
    ids = set(ids)
    if not ids:
        return {}
    return dict((await session.execute(select(Person.user_id, Person.full_name).where(Person.user_id.in_(ids)))).all())


async def summaries(session: AsyncSession, courses: Sequence[Node]) -> list[CourseSummary]:
    ids = [c.id for c in courses]
    if not ids:
        return []
    sections = dict(
        (
            await session.execute(
                select(Node.course_id, func.count()).where(Node.course_id.in_(ids), Node.kind == "section").group_by(Node.course_id)
            )
        ).all()
    )
    materials = dict(
        (
            await session.execute(
                select(Material.course_id, func.count()).where(Material.course_id.in_(ids)).group_by(Material.course_id)
            )
        ).all()
    )
    subjects = {
        s.id: s
        for s in (await session.execute(select(Subject).where(Subject.id.in_({c.subject_id for c in courses if c.subject_id})))).scalars()
    }
    authors = await names(session, {c.owner_id for c in courses})
    return [
        CourseSummary(
            id=c.id,
            title=c.title,
            description=c.description,
            subject=SubjectOut(id=subjects[c.subject_id].id, name=subjects[c.subject_id].name) if c.subject_id in subjects else None,
            owner_id=c.owner_id,
            author_name=authors.get(c.owner_id, UNKNOWN),
            status=c.status,
            review_comment=c.review_comment,
            theme=c.theme,
            sections_count=sections.get(c.id, 0),
            materials_count=materials.get(c.id, 0),
            updated_at=c.updated_at,
        )
        for c in courses
    ]


async def _marks(session: AsyncSession, principal: Principal | None, material_ids: list[UUID]) -> tuple[dict[UUID, int], set[UUID]]:
    """Прогресс (позиция видео) и избранное текущего пользователя."""
    if principal is None or not material_ids:
        return {}, set()
    progress = dict(
        (
            await session.execute(
                select(MaterialProgress.material_id, MaterialProgress.position_sec).where(
                    MaterialProgress.user_id == principal.user_id, MaterialProgress.material_id.in_(material_ids)
                )
            )
        ).all()
    )
    favorites = set(
        (
            await session.execute(
                select(Favorite.material_id).where(Favorite.user_id == principal.user_id, Favorite.material_id.in_(material_ids))
            )
        ).scalars()
    )
    return progress, favorites


async def course_tree(session: AsyncSession, course: Node, principal: Principal | None) -> CourseOut:
    # После изменений updated_at вычисляется базой — перечитываем курс явно (неявная подгрузка в async недоступна).
    await session.refresh(course)
    nodes = (
        await session.execute(select(Node).where(Node.course_id == course.id, Node.kind != "course").order_by(Node.position, Node.created_at))
    ).scalars().all()
    materials = (
        await session.execute(select(Material).where(Material.course_id == course.id).order_by(Material.position, Material.created_at))
    ).scalars().all()
    progress, favorites = await _marks(session, principal, [m.id for m in materials])

    by_module: dict[UUID, list[MaterialBrief]] = defaultdict(list)
    for m in materials:
        by_module[m.module_id].append(
            MaterialBrief(id=m.id, kind=m.kind, title=m.title, viewed=m.id in progress, favorite=m.id in favorites)
        )
    modules_by_section: dict[UUID, list[ModuleOut]] = defaultdict(list)
    for n in nodes:
        if n.kind == "module":
            modules_by_section[n.parent_id].append(
                ModuleOut(id=n.id, title=n.title, description=n.description, materials=by_module[n.id], origin_id=n.origin_id)
            )
    sections = [
        SectionOut(id=n.id, title=n.title, description=n.description, modules=modules_by_section[n.id])
        for n in nodes
        if n.kind == "section"
    ]
    summary = (await summaries(session, [course]))[0]
    revision = None
    if course.revision_of is None and principal and (course.owner_id == principal.user_id or access.is_staff(principal)):
        draft = await session.scalar(select(Node).where(Node.revision_of == course.id))
        if draft is not None:
            revision = RevisionRef(id=draft.id, status=draft.status, review_comment=draft.review_comment)
    return CourseOut(
        **summary.model_dump(),
        sections=sections,
        can_edit=access.can_edit(course, principal),
        viewed_count=len(progress),
        revision_of=course.revision_of,
        revision=revision,
    )


async def file_urls(material_list: Sequence[Material]) -> dict[str, str]:
    ids = [str(m.file_id) for m in material_list if m.file_id]
    if not ids:
        return {}
    try:
        found = await media.post("/internal/files/urls", json={"file_ids": ids})
    except ApiError:
        return {}  # хранилище недоступно — текст и ссылки всё равно покажем
    return {fid: f["url"] for fid, f in found.items()}


def material_out(m: Material, urls: dict[str, str], progress: dict[UUID, int], favorites: set[UUID]) -> MaterialOut:
    return MaterialOut(
        id=m.id,
        module_id=m.module_id,
        course_id=m.course_id,
        kind=m.kind,
        title=m.title,
        body=m.body,
        url=m.url,
        file=FileInfo(id=m.file_id, filename=m.file_name or "", mime=m.file_mime or "", size=m.file_size, url=urls.get(str(m.file_id)))
        if m.file_id
        else None,
        task_id=m.task_id,
        position_sec=progress.get(m.id, 0),
        viewed=m.id in progress,
        favorite=m.id in favorites,
    )


async def module_content(session: AsyncSession, module: Node, course: Node, principal: Principal | None) -> ModuleContent:
    materials = (
        await session.execute(select(Material).where(Material.module_id == module.id).order_by(Material.position, Material.created_at))
    ).scalars().all()
    progress, favorites = await _marks(session, principal, [m.id for m in materials])
    urls = await file_urls(materials)

    # Соседние модули в порядке курса — для кнопок «назад / дальше».
    nodes = (
        await session.execute(select(Node).where(Node.course_id == course.id, Node.kind != "course").order_by(Node.position, Node.created_at))
    ).scalars().all()
    order = []
    for section in (n for n in nodes if n.kind == "section"):
        order += [n for n in nodes if n.kind == "module" and n.parent_id == section.id]
    idx = next(i for i, n in enumerate(order) if n.id == module.id)
    section = next(n for n in nodes if n.id == module.parent_id)
    return ModuleContent(
        id=module.id,
        title=module.title,
        description=module.description,
        course_id=course.id,
        course_title=course.title,
        course_theme=course.theme,
        origin_id=module.origin_id,
        revision_of=course.revision_of,
        section_title=section.title,
        materials=[material_out(m, urls, progress, favorites) for m in materials],
        prev_module_id=order[idx - 1].id if idx > 0 else None,
        next_module_id=order[idx + 1].id if idx + 1 < len(order) else None,
        can_edit=access.can_edit(course, principal),
    )
