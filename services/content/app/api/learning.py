"""Прогресс и избранное ученика; отчёт о просмотрах для педагога."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import access, views
from ..deps import auth, classroom, db
from ..models import Favorite, Material, MaterialProgress, Node
from ..schemas import MaterialOut, ProgressReport, ProgressUpdate

router = APIRouter(tags=["learning"])


async def _readable_material(session: AsyncSession, material_id: UUID, principal: Principal) -> Material:
    material = await session.get(Material, material_id)
    if material is None:
        raise ApiError(404, "not_found", "Материал не найден")
    await access.readable_node(session, material.course_id, principal)
    return material


@router.put("/materials/{material_id}/progress", status_code=204)
async def save_progress(
    material_id: UUID,
    body: ProgressUpdate,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> None:
    """Отметить материал просмотренным; для видео — сохранить, на какой секунде остановился."""
    material = await _readable_material(session, material_id, principal)
    values = {"user_id": principal.user_id, "material_id": material.id, "course_id": material.course_id}
    update = {"updated_at": datetime.now(UTC)}
    if body.position_sec is not None:
        values["position_sec"] = update["position_sec"] = body.position_sec
    await session.execute(
        insert(MaterialProgress).values(**values).on_conflict_do_update(index_elements=["user_id", "material_id"], set_=update)
    )
    await session.commit()


@router.put("/materials/{material_id}/favorite", status_code=204)
async def add_favorite(
    material_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> None:
    material = await _readable_material(session, material_id, principal)
    await session.execute(
        insert(Favorite).values(user_id=principal.user_id, material_id=material.id).on_conflict_do_nothing()
    )
    await session.commit()


@router.delete("/materials/{material_id}/favorite", status_code=204)
async def remove_favorite(
    material_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> None:
    await session.execute(delete(Favorite).where(Favorite.user_id == principal.user_id, Favorite.material_id == material_id))
    await session.commit()


@router.get("/favorites", response_model=list[MaterialOut])
async def favorites(
    principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> list[MaterialOut]:
    rows = (
        await session.execute(
            select(Material)
            .join(Favorite, Favorite.material_id == Material.id)
            .where(Favorite.user_id == principal.user_id)
            .order_by(Favorite.created_at.desc())
        )
    ).scalars().all()
    # Избранное из курса, к которому пропал доступ (например, сняли с публикации), не показываем.
    visible = []
    for m in rows:
        course = await session.get(Node, m.course_id)
        if course and await access.can_read(session, course, principal):
            visible.append(m)
    progress = dict(
        (
            await session.execute(
                select(MaterialProgress.material_id, MaterialProgress.position_sec).where(
                    MaterialProgress.user_id == principal.user_id, MaterialProgress.material_id.in_([m.id for m in visible])
                )
            )
        ).all()
    )
    return [views.material_out(m, {}, progress, {m.id for m in visible}) for m in visible]


@router.get("/courses/{course_id}/progress", response_model=ProgressReport)
async def progress_report(
    course_id: UUID,
    group_id: UUID | None = None,
    student_id: UUID | None = None,
    principal: Principal = Depends(auth.require(ROLE_TEACHER)),
    session: AsyncSession = Depends(db.session),
) -> ProgressReport:
    """Педагог видит, какие материалы курса открыли ученики его группы (или его ученик)."""
    _, course = await access.readable_node(session, course_id, principal)
    if (group_id is None) == (student_id is None):
        raise ApiError(422, "invalid_target", "Выберите группу или ученика")
    if group_id:
        group = await classroom.get(f"/internal/groups/{group_id}", params={"teacher_id": str(principal.user_id)})
        students = [UUID(s) for s in group["member_ids"]]
    else:
        link = await classroom.get(
            "/internal/links", params={"teacher_id": str(principal.user_id), "student_id": str(student_id)}
        )
        if not link["active"]:
            raise ApiError(404, "student_not_found", "Ученик не привязан к вам")
        students = [student_id]

    materials = (
        await session.execute(
            select(Material, Node.title)
            .join(Node, Node.id == Material.module_id)
            .where(Material.course_id == course.id)
            .order_by(Node.position, Material.position)
        )
    ).all()
    viewed: dict[UUID, list[str]] = {s: [] for s in students}
    if students:
        rows = await session.execute(
            select(MaterialProgress.user_id, MaterialProgress.material_id).where(
                MaterialProgress.course_id == course.id, MaterialProgress.user_id.in_(students)
            )
        )
        for uid, mid in rows.all():
            viewed[uid].append(str(mid))
    names = await views.names(session, students)
    return ProgressReport(
        materials=[{"id": str(m.id), "title": m.title, "kind": m.kind, "module_title": title} for m, title in materials],
        students=sorted(
            ({"id": str(s), "full_name": names.get(s, "Ученик"), "viewed": viewed[s]} for s in students),
            key=lambda r: r["full_name"],
        ),
    )
