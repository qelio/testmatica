"""Администратор снимает любой курс с платформы без очереди модерации (ТЗ, раздел 2: «удаление любого контента»).
Курс не удаляется физически: у учеников сохраняется прогресс, автор видит причину, восстановить может администратор."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_ADMIN, Principal
from testmatica_common.errors import ApiError

from .. import access, views
from ..deps import auth, db, outbox
from ..models import PRIVATE, PUBLISHED, REJECTED, REMOVED
from ..schemas import CourseOut

router = APIRouter(prefix="/admin", tags=["admin"])
admin = auth.require(ROLE_ADMIN)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


async def _course(session: AsyncSession, course_id: UUID):
    node, course = await access.load_node(session, course_id, lock=True)
    if node.kind != "course":
        raise ApiError(404, "not_found", "Курс не найден")
    return course


@router.post("/courses/{course_id}/remove", response_model=CourseOut)
async def remove(course_id: UUID, body: ReasonIn, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> CourseOut:
    course = await _course(session, course_id)
    if course.status != REMOVED:
        course.removed_from = course.status
        course.status, course.review_comment = REMOVED, body.reason.strip()
        await outbox.event(session, "content.course.removed", {
            "course_id": str(course.id), "title": course.title, "author_id": str(course.owner_id), "reason": course.review_comment,
        }, actor_id=principal.user_id)
        await session.commit()
    return await views.course_tree(session, course, principal)


@router.post("/courses/{course_id}/restore", response_model=CourseOut)
async def restore(course_id: UUID, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> CourseOut:
    """Отменить снятие: курс возвращается в прежний статус (опубликованный — снова в библиотеку).
    Если он был на проверке — в приватную библиотеку автора (заявку из очереди уже сняли)."""
    course = await _course(session, course_id)
    if course.status != REMOVED:
        raise ApiError(409, "not_removed", "Курс не снят с платформы")
    course.status = course.removed_from if course.removed_from in (PUBLISHED, PRIVATE, REJECTED) else PRIVATE
    course.review_comment, course.removed_from = None, None
    await outbox.event(session, "content.course.restored", {
        "course_id": str(course.id), "title": course.title, "author_id": str(course.owner_id), "status": course.status,
    }, actor_id=principal.user_id)
    await session.commit()
    return await views.course_tree(session, course, principal)
