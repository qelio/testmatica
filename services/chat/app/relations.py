"""Реплики связей из identity и classroom и правило «кто кому может писать» (decisions.md, п. 12)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, delete, exists, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from testmatica_common.messaging import Envelope

from .models import (
    KIND_GROUP,
    Conversation,
    ConversationMember,
    Person,
    RelGroup,
    RelGroupMember,
    RelLink,
)


def _now() -> datetime:
    return datetime.now(UTC)


# ---------- события identity ----------


async def on_identity_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type not in ("identity.user.registered", "identity.user.snapshot", "identity.user.updated"):
        return
    d = envelope.data
    values = {"user_id": UUID(d["user_id"]), "full_name": d["full_name"], "login": d.get("login")}
    upd = {"full_name": values["full_name"], "login": values["login"]}
    if d.get("roles") is not None:
        values["roles"] = upd["roles"] = d["roles"]
    await session.execute(insert(Person).values(**values).on_conflict_do_update(index_elements=["user_id"], set_=upd))


# ---------- события classroom ----------


async def _group_conversation(session: AsyncSession, group_id: UUID) -> Conversation:
    """Групповой чат создаётся вместе с группой (один на группу)."""
    await session.execute(
        insert(Conversation).values(kind=KIND_GROUP, group_id=group_id).on_conflict_do_nothing(index_elements=["group_id"])
    )
    return (await session.execute(select(Conversation).where(Conversation.group_id == group_id))).scalar_one()


async def _join(session: AsyncSession, conversation_id: UUID, user_id: UUID, role: str) -> None:
    await session.execute(
        insert(ConversationMember)
        .values(conversation_id=conversation_id, user_id=user_id, role=role, joined_at=_now())
        .on_conflict_do_update(
            index_elements=["conversation_id", "user_id"],
            set_={"left_at": None, "role": role},
            where=ConversationMember.left_at.is_not(None) | (ConversationMember.role != role),
        )
    )


async def _leave(session: AsyncSession, conversation_id: UUID, user_id: UUID) -> None:
    await session.execute(
        update(ConversationMember)
        .where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id,
            ConversationMember.left_at.is_(None),
        )
        .values(left_at=_now())
    )


async def _remove_member(session: AsyncSession, group_id: UUID, student_id: UUID) -> None:
    await session.execute(
        delete(RelGroupMember).where(RelGroupMember.group_id == group_id, RelGroupMember.student_id == student_id)
    )
    conv = await _group_conversation(session, group_id)
    await _leave(session, conv.id, student_id)


async def on_classroom_event(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    t = envelope.type
    if t in ("classroom.group.created", "classroom.group.snapshot"):
        gid, teacher = UUID(d["group_id"]), UUID(d["teacher_id"])
        archived = bool(d.get("archived", False))
        await session.execute(
            insert(RelGroup)
            .values(id=gid, teacher_id=teacher, title=d["title"], archived=archived)
            .on_conflict_do_update(index_elements=["id"], set_={"title": d["title"], "archived": archived})
        )
        conv = await _group_conversation(session, gid)
        await _join(session, conv.id, teacher, "teacher")
    elif t == "classroom.group.updated":
        await session.execute(update(RelGroup).where(RelGroup.id == UUID(d["group_id"])).values(title=d["title"]))
    elif t in ("classroom.group.archived", "classroom.group.restored"):
        await session.execute(
            update(RelGroup).where(RelGroup.id == UUID(d["group_id"])).values(archived=t.endswith("archived"))
        )
    elif t in ("classroom.member.added", "classroom.member.snapshot"):
        gid, sid = UUID(d["group_id"]), UUID(d["student_id"])
        await session.execute(insert(RelGroupMember).values(group_id=gid, student_id=sid).on_conflict_do_nothing())
        conv = await _group_conversation(session, gid)
        await _join(session, conv.id, sid, "member")
    elif t == "classroom.member.removed":
        await _remove_member(session, UUID(d["group_id"]), UUID(d["student_id"]))
    elif t in ("classroom.link.created", "classroom.link.snapshot"):
        await session.execute(
            insert(RelLink)
            .values(teacher_id=UUID(d["teacher_id"]), student_id=UUID(d["student_id"]))
            .on_conflict_do_nothing()
        )
    elif t == "classroom.link.ended":
        teacher, sid = UUID(d["teacher_id"]), UUID(d["student_id"])
        await session.execute(delete(RelLink).where(RelLink.teacher_id == teacher, RelLink.student_id == sid))
        # Отвязанный ученик выходит из всех групп педагога (classroom не шлёт по ним member.removed).
        groups = await session.execute(
            select(RelGroupMember.group_id)
            .join(RelGroup, RelGroup.id == RelGroupMember.group_id)
            .where(RelGroup.teacher_id == teacher, RelGroupMember.student_id == sid)
        )
        for gid in list(groups.scalars()):
            await _remove_member(session, gid, sid)


# ---------- правило личных сообщений ----------


def _classmates_clause(a: UUID, b: UUID):
    m1, m2 = aliased(RelGroupMember), aliased(RelGroupMember)
    return exists(
        select(1)
        .select_from(m1)
        .join(m2, m2.group_id == m1.group_id)
        .join(RelGroup, RelGroup.id == m1.group_id)
        .where(m1.student_id == a, m2.student_id == b, RelGroup.archived.is_(False))
    )


async def can_message(session: AsyncSession, a: UUID, b: UUID) -> bool:
    """Писать можно привязанному педагогу/ученику и одногруппнику."""
    if a == b:
        return False
    linked = exists(
        select(1).where(
            or_(
                and_(RelLink.teacher_id == a, RelLink.student_id == b),
                and_(RelLink.teacher_id == b, RelLink.student_id == a),
            )
        )
    )
    return bool(await session.scalar(select(or_(linked, _classmates_clause(a, b)))))


async def contacts(session: AsyncSession, user_id: UUID) -> list[tuple[UUID, str, str]]:
    """(id, имя, кто это) — все, кому пользователь может написать."""
    found: dict[UUID, str] = {}
    for (sid,) in (await session.execute(select(RelLink.student_id).where(RelLink.teacher_id == user_id))).all():
        found.setdefault(sid, "ученик")
    for (tid,) in (await session.execute(select(RelLink.teacher_id).where(RelLink.student_id == user_id))).all():
        found.setdefault(tid, "педагог")
    m1, m2 = aliased(RelGroupMember), aliased(RelGroupMember)
    classmates = await session.execute(
        select(m2.student_id)
        .select_from(m1)
        .join(m2, m2.group_id == m1.group_id)
        .join(RelGroup, RelGroup.id == m1.group_id)
        .where(m1.student_id == user_id, m2.student_id != user_id, RelGroup.archived.is_(False))
        .distinct()
    )
    for (cid,) in classmates.all():
        found.setdefault(cid, "одногруппник")
    if not found:
        return []
    names = dict((await session.execute(select(Person.user_id, Person.full_name).where(Person.user_id.in_(found)))).all())
    result = [(uid, names.get(uid, "Пользователь"), who) for uid, who in found.items()]
    return sorted(result, key=lambda c: c[1])
