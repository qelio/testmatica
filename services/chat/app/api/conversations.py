from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError

from .. import realtime, relations
from ..deps import auth, db, media, outbox
from ..models import (
    KIND_DEAL,
    KIND_DIRECT,
    KIND_GROUP,
    Conversation,
    ConversationMember,
    Message,
    Person,
    RelGroup,
)
from ..schemas import Attachment, Contact, ConversationOut, DirectCreate, MessageCreate, MessageOut, ReadMark

router = APIRouter(tags=["chat"])

DELETED_TEXT = "Сообщение удалено"
PREVIEW = 120


def _now() -> datetime:
    return datetime.now(UTC)


async def _names(session: AsyncSession, ids) -> dict[UUID, str]:
    ids = set(ids)
    if not ids:
        return {}
    return dict((await session.execute(select(Person.user_id, Person.full_name).where(Person.user_id.in_(ids)))).all())


def _message_out(m: Message, names: dict[UUID, str], urls: dict[str, str] | None = None) -> MessageOut:
    deleted = m.deleted_at is not None
    urls = urls or {}
    return MessageOut(
        id=m.id,
        conversation_id=m.conversation_id,
        author_id=m.author_id,
        author_name=names.get(m.author_id, "Пользователь"),
        text=DELETED_TEXT if deleted else m.text,
        attachments=[] if deleted else [Attachment(**a, url=urls.get(a["id"])) for a in m.attachments],
        is_announcement=m.is_announcement,
        is_system=m.is_system,
        deleted=deleted,
        created_at=m.created_at,
    )


async def _attachment_urls(messages) -> dict[str, str]:
    """Временные ссылки на вложения. Если media недоступен — чат работает, просто без ссылок."""
    ids = [a["id"] for m in messages if m.deleted_at is None for a in m.attachments]
    if not ids:
        return {}
    try:
        found = await media.post("/internal/files/urls", json={"file_ids": ids})
    except ApiError:
        return {}
    return {fid: f["url"] for fid, f in found.items()}


async def _membership(session: AsyncSession, conversation_id: UUID, user_id: UUID) -> tuple[Conversation, ConversationMember]:
    row = (
        await session.execute(
            select(Conversation, ConversationMember)
            .join(ConversationMember, ConversationMember.conversation_id == Conversation.id)
            .where(
                Conversation.id == conversation_id,
                ConversationMember.user_id == user_id,
                ConversationMember.left_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise ApiError(404, "conversation_not_found", "Чат не найден")
    return row[0], row[1]


async def _can_write(session: AsyncSession, conv: Conversation, user_id: UUID, other: UUID | None) -> bool:
    if conv.kind == KIND_DEAL:
        return True  # переговоры по заявке — без привязки (решение №12)
    if conv.kind == KIND_DIRECT:
        # Переписка остаётся, но писать можно, только пока есть связь.
        return other is not None and await relations.can_message(session, user_id, other)
    group = await session.get(RelGroup, conv.group_id)
    return group is not None and not group.archived


async def _other_members(session: AsyncSession, conversation_ids: list[UUID], user_id: UUID) -> dict[UUID, UUID]:
    """Собеседник в личных диалогах."""
    if not conversation_ids:
        return {}
    rows = await session.execute(
        select(ConversationMember.conversation_id, ConversationMember.user_id).where(
            ConversationMember.conversation_id.in_(conversation_ids), ConversationMember.user_id != user_id
        )
    )
    return dict(rows.all())


async def _serialize(session: AsyncSession, rows: list[tuple[Conversation, ConversationMember]], user_id: UUID) -> list[ConversationOut]:
    ids = [c.id for c, _ in rows]
    direct_ids = [c.id for c, _ in rows if c.kind in (KIND_DIRECT, KIND_DEAL)]
    others = await _other_members(session, direct_ids, user_id)
    groups = {
        g.id: g
        for g in (
            await session.execute(select(RelGroup).where(RelGroup.id.in_([c.group_id for c, _ in rows if c.group_id])))
        ).scalars()
    }

    # Последнее сообщение каждого чата и закреплённые.
    last = {}
    if ids:
        ranked = (
            select(Message, func.row_number().over(partition_by=Message.conversation_id, order_by=Message.created_at.desc()).label("rn"))
            .where(Message.conversation_id.in_(ids))
            .subquery()
        )
        for m in (await session.execute(select(Message).join(ranked, ranked.c.id == Message.id).where(ranked.c.rn == 1))).scalars():
            last[m.conversation_id] = m
    pinned_ids = [c.pinned_message_id for c, _ in rows if c.pinned_message_id]
    pinned = {m.id: m for m in (await session.execute(select(Message).where(Message.id.in_(pinned_ids)))).scalars()} if pinned_ids else {}

    # Непрочитанные: чужие сообщения после last_read_at (или после вступления в чат).
    unread = {}
    if ids:
        since = func.coalesce(ConversationMember.last_read_at, ConversationMember.joined_at)
        q = (
            select(Message.conversation_id, func.count())
            .join(
                ConversationMember,
                and_(ConversationMember.conversation_id == Message.conversation_id, ConversationMember.user_id == user_id),
            )
            .where(
                Message.conversation_id.in_(ids),
                Message.author_id != user_id,
                Message.deleted_at.is_(None),
                Message.created_at > since,
            )
            .group_by(Message.conversation_id)
        )
        unread = dict((await session.execute(q)).all())

    names = await _names(
        session,
        set(others.values()) | {m.author_id for m in last.values()} | {m.author_id for m in pinned.values()},
    )
    result = []
    for conv, member in rows:
        other = others.get(conv.id)
        if conv.kind == KIND_GROUP and conv.group_id in groups:
            title = groups[conv.group_id].title
        elif conv.kind == KIND_DEAL:
            title = f"{names.get(other, 'Пользователь')} · {conv.title}"
        else:
            title = names.get(other, "Пользователь")
        pin = pinned.get(conv.pinned_message_id) if conv.pinned_message_id else None
        result.append(
            ConversationOut(
                id=conv.id,
                kind=conv.kind,
                title=title,
                group_id=conv.group_id,
                other_user_id=other,
                my_role=member.role,
                can_write=await _can_write(session, conv, user_id, other),
                unread=unread.get(conv.id, 0),
                last_message=_message_out(last[conv.id], names) if conv.id in last else None,
                pinned=_message_out(pin, names) if pin and pin.deleted_at is None else None,
                last_message_at=conv.last_message_at,
            )
        )
    return result


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> list[ConversationOut]:
    rows = (
        await session.execute(
            select(Conversation, ConversationMember)
            .join(ConversationMember, ConversationMember.conversation_id == Conversation.id)
            .where(ConversationMember.user_id == principal.user_id, ConversationMember.left_at.is_(None))
            # Групповые чаты видны сразу; личные — когда в них появилось первое сообщение.
            .where(or_(Conversation.kind == KIND_GROUP, Conversation.last_message_at.is_not(None)))
            .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.created_at.desc())
        )
    ).all()
    return await _serialize(session, [(c, m) for c, m in rows], principal.user_id)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> ConversationOut:
    conv, member = await _membership(session, conversation_id, principal.user_id)
    return (await _serialize(session, [(conv, member)], principal.user_id))[0]


@router.get("/contacts", response_model=list[Contact])
async def list_contacts(
    principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> list[Contact]:
    return [Contact(id=i, full_name=n, relation=r) for i, n, r in await relations.contacts(session, principal.user_id)]


@router.post("/conversations/direct", response_model=ConversationOut)
async def open_direct(
    body: DirectCreate, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> ConversationOut:
    """Открыть (или создать) личный диалог с пользователем, с которым есть связь."""
    me, other = principal.user_id, body.user_id
    if not await relations.can_message(session, me, other):
        raise ApiError(403, "not_allowed", "Написать можно только своим педагогам, ученикам и одногруппникам")
    pair_key = ":".join(sorted((str(me), str(other))))
    await session.execute(
        insert(Conversation).values(kind=KIND_DIRECT, pair_key=pair_key).on_conflict_do_nothing(index_elements=["pair_key"])
    )
    conv = (await session.execute(select(Conversation).where(Conversation.pair_key == pair_key))).scalar_one()
    for uid in (me, other):
        await session.execute(
            insert(ConversationMember)
            .values(conversation_id=conv.id, user_id=uid, role="member", joined_at=conv.created_at or _now())
            .on_conflict_do_nothing()
        )
    await session.commit()
    conv, member = await _membership(session, conv.id, me)
    return (await _serialize(session, [(conv, member)], me))[0]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: UUID,
    before: datetime | None = None,
    limit: int = Query(50, ge=1, le=100),
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> list[MessageOut]:
    """Сообщения от новых к старым; для подгрузки истории передайте before = время самого старого."""
    await _membership(session, conversation_id, principal.user_id)
    query = select(Message).where(Message.conversation_id == conversation_id)
    if before is not None:
        query = query.where(Message.created_at < before)
    rows = (await session.execute(query.order_by(Message.created_at.desc()).limit(limit))).scalars().all()
    names = await _names(session, {m.author_id for m in rows})
    urls = await _attachment_urls(rows)
    return [_message_out(m, names, urls) for m in rows]


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(
    conversation_id: UUID,
    body: MessageCreate,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> MessageOut:
    conv, member = await _membership(session, conversation_id, principal.user_id)
    others = await _other_members(session, [conv.id], principal.user_id) if conv.kind in (KIND_DIRECT, KIND_DEAL) else {}
    if not await _can_write(session, conv, principal.user_id, others.get(conv.id)):
        raise ApiError(403, "read_only", "В этот чат больше нельзя писать")
    if body.announcement and (conv.kind != KIND_GROUP or member.role != "teacher"):
        raise ApiError(403, "forbidden", "Объявления публикует педагог в групповом чате")

    attachments = []
    if body.attachment_ids:
        # media проверит, что файлы загрузил сам автор и именно как вложения в чат.
        claimed = await media.post(
            "/internal/files/claim",
            json={
                "owner_id": str(principal.user_id),
                "purpose": "chat_attachment",
                "file_ids": [str(i) for i in body.attachment_ids],
                "claimed_by": "chat",
            },
        )
        attachments = [{k: f[k] for k in ("id", "filename", "mime", "size")} for f in claimed]
    msg = Message(
        conversation_id=conv.id,
        author_id=principal.user_id,
        text=body.text,
        attachments=attachments,
        is_announcement=body.announcement,
        created_at=_now(),
    )
    session.add(msg)
    await session.flush()
    conv.last_message_at = msg.created_at
    member.last_read_at = msg.created_at
    if body.announcement:
        conv.pinned_message_id = msg.id

    recipients = list(
        (
            await session.execute(
                select(ConversationMember.user_id).where(
                    ConversationMember.conversation_id == conv.id,
                    ConversationMember.user_id != principal.user_id,
                    ConversationMember.left_at.is_(None),
                )
            )
        ).scalars()
    )
    names = await _names(session, [principal.user_id])
    out = _message_out(msg, names, await _attachment_urls([msg]))
    title = (await session.get(RelGroup, conv.group_id)).title if conv.kind == KIND_GROUP else out.author_name

    # В аудит — только факт, без текста. Текст — в команде уведомлений (она не попадает в аудит).
    await outbox.event(
        session,
        "chat.message.created",
        {"message_id": str(msg.id), "conversation_id": str(conv.id), "kind": conv.kind, "announcement": body.announcement},
        actor_id=principal.user_id,
    )
    if recipients:
        text = body.text or "📎 " + ", ".join(a["filename"] for a in attachments)
        preview = text if len(text) <= PREVIEW else text[: PREVIEW - 1] + "…"
        await outbox.command(
            session,
            queue="notification.inapp",
            type="notification.inapp.send",
            data={
                "user_ids": [str(u) for u in recipients],
                "kind": "announcement" if body.announcement else "message",
                "title": f"Объявление: {title}" if body.announcement else f"Новое сообщение: {title}",
                "body": preview if conv.kind in (KIND_DIRECT, KIND_DEAL) or body.announcement else f"{out.author_name}: {preview}",
                "payload": {"conversation_id": str(conv.id)},
                # Одно непрочитанное уведомление на чат, а не на каждое сообщение.
                "coalesce_key": None if body.announcement else f"chat:{conv.id}",
            },
            actor_id=principal.user_id,
        )
    await session.commit()
    await realtime.publish(
        [*recipients, principal.user_id],
        {"type": "message", "conversation_id": str(conv.id), "message": out.model_dump(mode="json")},
    )
    return out


@router.post("/conversations/{conversation_id}/read", status_code=204)
async def mark_read(
    conversation_id: UUID,
    body: ReadMark,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> None:
    _, member = await _membership(session, conversation_id, principal.user_id)
    at = body.at or _now()
    if member.last_read_at is None or at > member.last_read_at:
        member.last_read_at = at
        await session.commit()


@router.delete("/conversations/{conversation_id}/pin", status_code=204)
async def unpin(
    conversation_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> None:
    conv, member = await _membership(session, conversation_id, principal.user_id)
    if member.role != "teacher":
        raise ApiError(403, "forbidden", "Открепить объявление может педагог")
    conv.pinned_message_id = None
    await session.commit()
    await realtime.publish([principal.user_id], {"type": "pinned", "conversation_id": str(conv.id), "message": None})


@router.delete("/messages/{message_id}", status_code=204)
async def delete_message(
    message_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> None:
    msg = await session.get(Message, message_id)
    if msg is None or msg.author_id != principal.user_id or msg.deleted_at is not None:
        raise ApiError(404, "message_not_found", "Сообщение не найдено")
    conv, _ = await _membership(session, msg.conversation_id, principal.user_id)
    msg.deleted_at = _now()
    if conv.pinned_message_id == msg.id:
        conv.pinned_message_id = None
    await outbox.event(
        session,
        "chat.message.deleted",
        {"message_id": str(msg.id), "conversation_id": str(conv.id)},
        actor_id=principal.user_id,
    )
    await session.commit()
    members = (
        await session.execute(
            select(ConversationMember.user_id).where(
                ConversationMember.conversation_id == conv.id, ConversationMember.left_at.is_(None)
            )
        )
    ).scalars()
    await realtime.publish(
        list(members),
        {"type": "deleted", "conversation_id": str(conv.id), "message_id": str(msg.id)},
    )


@router.get("/conversations/{conversation_id}/attachments/{file_id}", response_model=Attachment)
async def attachment(
    conversation_id: UUID,
    file_id: UUID,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> Attachment:
    """Свежая ссылка на вложение (если старая истекла). Только участникам чата."""
    await _membership(session, conversation_id, principal.user_id)
    msg = (
        await session.execute(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.deleted_at.is_(None),
                Message.attachments.contains([{"id": str(file_id)}]),
            )
        )
    ).scalars().first()
    if msg is None:
        raise ApiError(404, "attachment_not_found", "Вложение не найдено")
    meta = next(a for a in msg.attachments if a["id"] == str(file_id))
    urls = await _attachment_urls([msg])
    return Attachment(**meta, url=urls.get(str(file_id)))
