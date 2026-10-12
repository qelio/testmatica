"""Черновик изменений опубликованного курса (решение №46).

Автор правит копию курса; ученики и педагоги видят опубликованную версию, пока модератор не примет черновик.
Принятый черновик переносится в опубликованный курс с сохранением id разделов, модулей и материалов —
на них держатся прогресс учеников, избранное и привязка тестов к модулям (assessment)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.ids import uuid7

from .models import PRIVATE, PUBLISHED, Material, Node

COURSE_FIELDS = ("title", "description", "subject_id", "theme")
NODE_FIELDS = ("title", "description", "position")
MATERIAL_FIELDS = ("kind", "title", "body", "file_id", "file_name", "file_mime", "file_size", "url", "task_id", "position")


async def draft_of(session: AsyncSession, live: Node) -> Node | None:
    return await session.scalar(select(Node).where(Node.revision_of == live.id))


async def create(session: AsyncSession, live: Node) -> Node:
    """Копия опубликованного курса — черновик изменений (у копий — ссылки на оригиналы)."""
    draft_id = uuid7()
    draft = Node(
        id=draft_id, kind="course", course_id=draft_id, owner_id=live.owner_id, status=PRIVATE, revision_of=live.id,
        **{f: getattr(live, f) for f in COURSE_FIELDS},
    )
    session.add(draft)
    nodes = (await session.execute(select(Node).where(Node.course_id == live.id, Node.kind != "course"))).scalars().all()
    mapping = {live.id: draft_id}
    for n in sorted(nodes, key=lambda n: 0 if n.kind == "section" else 1):  # разделы — раньше своих модулей
        copy_id = uuid7()
        mapping[n.id] = copy_id
        session.add(Node(
            id=copy_id, kind=n.kind, parent_id=mapping[n.parent_id], course_id=draft_id, owner_id=n.owner_id, origin_id=n.id,
            **{f: getattr(n, f) for f in NODE_FIELDS},
        ))
    await session.flush()
    for m in (await session.execute(select(Material).where(Material.course_id == live.id))).scalars():
        session.add(Material(
            module_id=mapping[m.module_id], course_id=draft_id, origin_id=m.id, **{f: getattr(m, f) for f in MATERIAL_FIELDS},
        ))
    await session.flush()
    return draft


async def apply(session: AsyncSession, draft: Node) -> Node:
    """Перенести принятый черновик в опубликованный курс и удалить черновик. Возвращает опубликованный курс."""
    live = await session.get(Node, draft.revision_of, with_for_update=True)
    for f in COURSE_FIELDS:
        setattr(live, f, getattr(draft, f))

    draft_nodes = (await session.execute(select(Node).where(Node.course_id == draft.id, Node.kind != "course"))).scalars().all()
    live_nodes = {n.id: n for n in (await session.execute(
        select(Node).where(Node.course_id == live.id, Node.kind != "course")
    )).scalars()}
    # Узел черновика → узел опубликованной версии: оригинал или сам узел (новый — переезжает в курс).
    target = {draft.id: live.id}
    for n in draft_nodes:
        target[n.id] = n.origin_id if n.origin_id in live_nodes else n.id
    kept_nodes = set()
    for n in sorted(draft_nodes, key=lambda n: 0 if n.kind == "section" else 1):
        parent = target[n.parent_id]
        if target[n.id] != n.id:  # изменённый оригинал
            orig = live_nodes[target[n.id]]
            for f in NODE_FIELDS:
                setattr(orig, f, getattr(n, f))
            orig.parent_id = parent
        else:  # новый раздел или модуль
            n.course_id, n.parent_id, n.origin_id = live.id, parent, None
        kept_nodes.add(target[n.id])
    await session.flush()

    draft_materials = (await session.execute(select(Material).where(Material.course_id == draft.id))).scalars().all()
    live_materials = {m.id: m for m in (await session.execute(select(Material).where(Material.course_id == live.id))).scalars()}
    kept_materials = set()
    for m in draft_materials:
        module = target[m.module_id]
        if m.origin_id in live_materials:
            orig = live_materials[m.origin_id]
            for f in MATERIAL_FIELDS:
                setattr(orig, f, getattr(m, f))
            orig.module_id = module
            kept_materials.add(orig.id)
        else:
            m.module_id, m.course_id, m.origin_id = module, live.id, None
            kept_materials.add(m.id)
    await session.flush()

    # Удалённое в черновике — удаляется и из опубликованной версии (вместе с прогрессом учеников по нему).
    for mid, m in live_materials.items():
        if mid not in kept_materials:
            await session.delete(m)
    await session.flush()
    for nid, n in sorted(live_nodes.items(), key=lambda kv: 0 if kv[1].kind == "module" else 1):
        if nid not in kept_nodes:
            await session.delete(n)
    await session.flush()

    # Остаток черновика — копии, уже перенесённые в оригиналы.
    await session.execute(Material.__table__.delete().where(Material.course_id == draft.id))
    await session.execute(Node.__table__.delete().where(Node.course_id == draft.id, Node.kind == "module"))
    await session.execute(Node.__table__.delete().where(Node.course_id == draft.id, Node.kind == "section"))
    await session.delete(draft)
    await session.flush()
    return live


async def publish(session: AsyncSession, course: Node) -> Node:
    """Опубликовать курс; черновик изменений — перенести в опубликованную версию. Возвращает опубликованный курс."""
    if course.revision_of is None:
        course.status = PUBLISHED
        course.published_at = datetime.now(UTC)
        return course
    live = await apply(session, course)
    live.updated_at = datetime.now(UTC)
    return live
