"""Служебные команды.

    docker compose exec classroom python -m app.cli publish-snapshot
"""

import argparse
import asyncio

from sqlalchemy import select

from .deps import db, outbox
from .models import LINK_ACTIVE, Group, GroupMember, TeacherStudentLink


async def _publish_snapshot() -> None:
    """Разослать текущие группы, составы и привязки событиями *.snapshot —
    чтобы новый сервис (например, chat) заполнил свои реплики."""
    async with db.sessionmaker() as session:
        groups = (await session.execute(select(Group))).scalars().all()
        for g in groups:
            await outbox.event(
                session,
                "classroom.group.snapshot",
                {
                    "group_id": str(g.id),
                    "teacher_id": str(g.teacher_id),
                    "title": g.title,
                    "paid": g.paid,
                    "archived": g.archived_at is not None,
                },
            )
        members = (await session.execute(select(GroupMember).where(GroupMember.left_at.is_(None)))).scalars().all()
        teacher_of = {g.id: g.teacher_id for g in groups}
        for m in members:
            await outbox.event(
                session,
                "classroom.member.snapshot",
                {"group_id": str(m.group_id), "teacher_id": str(teacher_of[m.group_id]), "student_id": str(m.student_id)},
            )
        links = (
            await session.execute(select(TeacherStudentLink).where(TeacherStudentLink.status == LINK_ACTIVE))
        ).scalars().all()
        for link in links:
            await outbox.event(
                session,
                "classroom.link.snapshot",
                {"link_id": str(link.id), "teacher_id": str(link.teacher_id), "student_id": str(link.student_id)},
            )
        await session.commit()
        print(f"Опубликовано: групп {len(groups)}, участников {len(members)}, привязок {len(links)}")
    await db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("publish-snapshot", help="Разослать группы, составы и привязки другим сервисам")
    args = parser.parse_args()
    if args.command == "publish-snapshot":
        asyncio.run(_publish_snapshot())


if __name__ == "__main__":
    main()
