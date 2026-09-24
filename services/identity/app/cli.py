"""Служебные команды.

    docker compose exec identity python -m app.cli create-user \
        --email admin@testmatica.local --name "Администратор" --role admin
"""

import argparse
import asyncio
import getpass
from datetime import UTC, datetime

from .deps import db
from .models import ROLES, STATUS_ACTIVE
from .security import hash_password
from .users import create_user, find_by_email


async def _create_user(email: str, name: str, role: str, password: str) -> None:
    async with db.sessionmaker() as session:
        if await find_by_email(session, email):
            raise SystemExit(f"Пользователь {email} уже существует")
        user = await create_user(
            session,
            email=email,
            password_hash=hash_password(password),
            full_name=name,
            roles=[role],
            status=STATUS_ACTIVE,
            email_verified_at=datetime.now(UTC),
            two_factor_method="email",
        )
        await session.commit()
        print(f"Создан пользователь {user.email} ({role}), id={user.id}")
    await db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-user", help="Создать активного пользователя (например, администратора)")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--role", choices=ROLES, required=True)
    create.add_argument("--password", help="Если не указан — будет запрошен")
    args = parser.parse_args()

    if args.command == "create-user":
        password = args.password or getpass.getpass("Пароль: ")
        asyncio.run(_create_user(args.email, args.name, args.role, password))


if __name__ == "__main__":
    main()
