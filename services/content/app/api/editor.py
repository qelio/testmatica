"""Редактирование библиотеки автором и отправка курса в публичную библиотеку."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError
from testmatica_common.ids import uuid7

from .. import access, revisions, views
from ..deps import assessment, auth, db, media, outbox
from ..models import CHILD_KIND, FILE_KINDS, PENDING, PRIVATE, PUBLISHED, REJECTED, Material, Node, Subject
from ..schemas import (
    CourseCreate,
    CourseOut,
    MaterialCreate,
    MaterialOut,
    MaterialUpdate,
    Move,
    NodeCreate,
    NodeUpdate,
)

router = APIRouter(tags=["editor"])


def _author(principal: Principal) -> None:
    if not access.can_author(principal):
        raise ApiError(403, "forbidden", "Создавать материалы могут педагоги")


async def _next_position(session: AsyncSession, model, **where) -> int:
    query = select(func.coalesce(func.max(model.position), -1))
    for field, value in where.items():
        query = query.where(getattr(model, field) == value)
    return (await session.scalar(query)) + 1


async def _check_subject(session: AsyncSession, subject_id: UUID | None) -> None:
    if subject_id and await session.get(Subject, subject_id) is None:
        raise ApiError(422, "invalid_subject", "Неизвестный предмет")


def _touch(course: Node) -> None:
    course.updated_at = datetime.now(UTC)


# ---------- курсы, разделы, модули ----------


@router.post("/courses", response_model=CourseOut, status_code=201)
async def create_course(
    body: CourseCreate, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> CourseOut:
    _author(principal)
    await _check_subject(session, body.subject_id)
    cid = uuid7()
    course = Node(
        id=cid, kind="course", course_id=cid, owner_id=principal.user_id, title=body.title,
        description=body.description, subject_id=body.subject_id, status=PRIVATE, theme=body.theme,
    )
    session.add(course)
    await session.commit()
    return await views.course_tree(session, course, principal)


@router.post("/nodes/{parent_id}/children", response_model=CourseOut, status_code=201)
async def add_child(
    parent_id: UUID,
    body: NodeCreate,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> CourseOut:
    """Курс → раздел, раздел → модуль."""
    parent, course = await access.editable_node(session, parent_id, principal)
    kind = CHILD_KIND.get(parent.kind)
    if kind is None:
        raise ApiError(422, "invalid_parent", "В модуль добавляются материалы, а не разделы")
    session.add(
        Node(
            kind=kind, parent_id=parent.id, course_id=course.id, owner_id=course.owner_id, title=body.title,
            description=body.description, position=await _next_position(session, Node, parent_id=parent.id),
        )
    )
    _touch(course)
    await session.commit()
    return await views.course_tree(session, course, principal)


@router.patch("/nodes/{node_id}", response_model=CourseOut)
async def update_node(
    node_id: UUID,
    body: NodeUpdate,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> CourseOut:
    node, course = await access.editable_node(session, node_id, principal)
    data = body.model_dump(exclude_unset=True)
    if data.get("title"):
        node.title = data["title"]
    if "description" in data:
        node.description = data["description"] or ""
    if "subject_id" in data and node.kind == "course":
        await _check_subject(session, data["subject_id"])
        node.subject_id = data["subject_id"]
    if data.get("theme") and node.kind == "course":
        node.theme = data["theme"]
    _touch(course)
    await session.commit()
    return await views.course_tree(session, course, principal)


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(
    node_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> None:
    node, course = await access.editable_node(session, node_id, principal)
    if node.kind == "course":
        # Курс удаляется целиком вместе с материалами и прогрессом учеников.
        await session.execute(Material.__table__.delete().where(Material.course_id == course.id))
        await session.execute(Node.__table__.delete().where(Node.course_id == course.id, Node.kind == "module"))
        await session.execute(Node.__table__.delete().where(Node.course_id == course.id, Node.kind == "section"))
        await outbox.event(session, "content.course.deleted", {"course_id": str(course.id)}, actor_id=principal.user_id)
    else:
        _touch(course)
    await session.delete(node)
    await session.commit()


@router.post("/nodes/{node_id}/move", response_model=CourseOut)
async def move_node(
    node_id: UUID,
    body: Move,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> CourseOut:
    node, course = await access.editable_node(session, node_id, principal)
    if node.kind == "course":
        raise ApiError(422, "invalid_move", "Курс не перемещается")
    siblings = (
        await session.execute(select(Node).where(Node.parent_id == node.parent_id).order_by(Node.position, Node.created_at))
    ).scalars().all()
    _swap(list(siblings), node, body.direction)
    _touch(course)
    await session.commit()
    return await views.course_tree(session, course, principal)


def _swap(items: list, item, direction: str) -> None:
    """Поменять элемент местами с соседом; позиции перенумеровываются подряд."""
    idx = items.index(item)
    other = idx - 1 if direction == "up" else idx + 1
    if 0 <= other < len(items):
        items[idx], items[other] = items[other], items[idx]
    for pos, it in enumerate(items):
        it.position = pos


# ---------- материалы ----------


@router.post("/modules/{module_id}/materials", response_model=MaterialOut, status_code=201)
async def add_material(
    module_id: UUID,
    body: MaterialCreate,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> MaterialOut:
    module, course = await access.editable_node(session, module_id, principal)
    if module.kind != "module":
        raise ApiError(422, "invalid_parent", "Материалы добавляются в модуль")
    title = body.title
    task_id = None
    if body.kind == "task":
        # В курсы — только задачи с автопроверкой; своя (в любом статусе) или опубликованная в банке.
        brief = await _task_briefs(course.owner_id, [body.task_id])
        task = brief.get(str(body.task_id))
        if task is None or not task["usable"]:
            raise ApiError(422, "task_not_available", "Задача не найдена в вашем банке или в публичном")
        if not task["auto_checked"]:
            raise ApiError(422, "task_manual_check", "В курс можно добавить только задачи с автопроверкой: выбор ответа, короткий ответ, код")
        title, task_id = title or task["title"], body.task_id
    material = Material(
        module_id=module.id, course_id=course.id, kind=body.kind, title=title, body=body.body.strip(), task_id=task_id,
        url=body.url if body.kind == "link" else None,
        position=await _next_position(session, Material, module_id=module.id),
    )
    if body.kind in FILE_KINDS:
        # media проверит, что файл загрузил автор и именно как учебный материал.
        claimed = (
            await media.post(
                "/internal/files/claim",
                json={"owner_id": str(principal.user_id), "purpose": "material", "file_ids": [str(body.file_id)], "claimed_by": "content"},
            )
        )[0]
        if body.kind == "video" and not claimed["mime"].startswith("video/"):
            raise ApiError(422, "invalid_file", "Для видео загрузите файл MP4, WebM или MOV")
        if body.kind == "pdf" and claimed["mime"] != "application/pdf":
            raise ApiError(422, "invalid_file", "Нужен файл PDF")
        material.file_id = body.file_id
        material.file_name, material.file_mime, material.file_size = claimed["filename"], claimed["mime"], claimed["size"]
    session.add(material)
    _touch(course)
    await session.commit()
    urls = await views.file_urls([material])
    return views.material_out(material, urls, {}, set())


@router.patch("/materials/{material_id}", response_model=MaterialOut)
async def update_material(
    material_id: UUID,
    body: MaterialUpdate,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> MaterialOut:
    material, course = await access.editable_material(session, material_id, principal)
    data = body.model_dump(exclude_unset=True)
    if data.get("title"):
        material.title = data["title"]
    if "body" in data and material.kind in ("text", "card"):
        if not (data["body"] or "").strip():
            raise ApiError(422, "empty_body", "Текст не может быть пустым")
        material.body = data["body"].strip()
    if "url" in data and material.kind == "link":
        url = (data["url"] or "").strip()
        if not url.startswith(("https://", "http://")):
            raise ApiError(422, "invalid_url", "Ссылка должна начинаться с https://")
        material.url = url
    _touch(course)
    await session.commit()
    return views.material_out(material, await views.file_urls([material]), {}, set())


@router.delete("/materials/{material_id}", status_code=204)
async def delete_material(
    material_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> None:
    material, course = await access.editable_material(session, material_id, principal)
    await session.delete(material)
    _touch(course)
    await session.commit()


@router.post("/materials/{material_id}/move", status_code=204)
async def move_material(
    material_id: UUID,
    body: Move,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> None:
    material, course = await access.editable_material(session, material_id, principal)
    siblings = (
        await session.execute(
            select(Material).where(Material.module_id == material.module_id).order_by(Material.position, Material.created_at)
        )
    ).scalars().all()
    _swap(list(siblings), material, body.direction)
    _touch(course)
    await session.commit()


async def _task_briefs(owner_id: UUID, task_ids: list[UUID]) -> dict[str, dict]:
    if not task_ids:
        return {}
    rows = await assessment.post(
        "/internal/tasks/lookup", json={"task_ids": [str(t) for t in task_ids], "user_id": str(owner_id)}
    )
    return {r["id"]: r for r in rows}


# ---------- публикация ----------


@router.post("/courses/{course_id}/submit", response_model=CourseOut)
async def submit(
    course_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> CourseOut:
    """Отправить курс в публичную библиотеку. Педагогов проверяет модератор;
    курсы штатных редакторов (модераторов) публикуются сразу."""
    node, course = await access.editable_node(session, course_id, principal)
    if node.kind != "course" or course.status not in (PRIVATE, REJECTED):
        raise ApiError(409, "invalid_status", "Курс уже опубликован или на проверке")
    materials = await session.scalar(select(func.count()).select_from(Material).where(Material.course_id == course.id))
    if not materials:
        raise ApiError(422, "course_empty", "Добавьте в курс хотя бы один материал")
    if course.subject_id is None:
        raise ApiError(422, "subject_required", "Укажите предмет курса — по нему курс ищут в библиотеке")

    # Задачи курса: чужие должны быть уже опубликованы, свои приватные уходят на проверку вместе с курсом.
    task_ids = list(
        (
            await session.execute(select(Material.task_id).where(Material.course_id == course.id, Material.task_id.is_not(None)))
        ).scalars()
    )
    briefs = await _task_briefs(course.owner_id, task_ids)
    unavailable = [str(t) for t in task_ids if str(t) not in briefs or not briefs[str(t)]["usable"]]
    if unavailable:
        raise ApiError(422, "tasks_unavailable", "Некоторые задачи курса удалены или недоступны — уберите их", {"task_ids": unavailable})
    own_private = [tid for tid, b in briefs.items() if b["owner_id"] == str(course.owner_id) and b["status"] != "published"]
    data = {
        "course_id": str(course.id), "author_id": str(course.owner_id), "materials_count": materials,
        "title": f"Изменения курса «{course.title}»" if course.revision_of else course.title,
        "tasks_count": len(task_ids), "task_ids": own_private,
        # Черновик изменений опубликованного курса (решение №46): id опубликованной версии — по нему assessment
        # находит тесты курса, чьи изменения и задачи проверяются вместе с черновиком.
        "revision_of": str(course.revision_of) if course.revision_of else None,
    }
    if access.is_staff(principal):
        # Курсы штатных редакторов публикуются сразу; черновик — сразу переносится в опубликованную версию.
        course.review_comment = None
        live = await revisions.publish(session, course)
        await outbox.event(session, "content.course.published", data | {"course_id": str(live.id), "revision_id": data["course_id"]
                                                                          if course is not live else None},
                           actor_id=principal.user_id)
        await session.commit()
        return await views.course_tree(session, live, principal)
    course.status = PENDING
    course.review_comment = None
    await outbox.event(session, "content.course.submitted", data, actor_id=principal.user_id)
    await session.commit()
    return await views.course_tree(session, course, principal)


@router.post("/courses/{course_id}/revision", response_model=CourseOut, status_code=201)
async def start_revision(
    course_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> CourseOut:
    """Черновик изменений опубликованного курса (решение №46): автор правит копию, ученики видят прежнюю версию,
    пока модератор не примет изменения. Черновик уже есть — возвращается он."""
    node, course = await access.load_node(session, course_id, lock=True)
    if node.kind != "course" or course.owner_id != principal.user_id:
        raise ApiError(404, "not_found", "Курс не найден")
    if course.status != PUBLISHED or course.revision_of is not None:
        raise ApiError(409, "invalid_status", "Черновик изменений — только у опубликованного курса")
    draft = await revisions.draft_of(session, course) or await revisions.create(session, course)
    await session.commit()
    return await views.course_tree(session, draft, principal)


@router.post("/courses/{course_id}/unpublish", response_model=CourseOut)
async def unpublish(
    course_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> CourseOut:
    """Вернуть курс в приватную библиотеку (автор) или снять с публикации (модератор)."""
    node, course = await access.load_node(session, course_id, lock=True)
    if node.kind != "course" or not (course.owner_id == principal.user_id or access.is_staff(principal)):
        raise ApiError(404, "not_found", "Курс не найден")
    if course.status not in (PUBLISHED, PENDING):
        raise ApiError(409, "invalid_status", "Курс не опубликован")
    course.status = PRIVATE
    await outbox.event(
        session,
        "content.course.unpublished",
        {"course_id": str(course.id), "title": course.title, "author_id": str(course.owner_id)},
        actor_id=principal.user_id,
    )
    await session.commit()
    return await views.course_tree(session, course, principal)
