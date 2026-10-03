"""task numbers

Revision ID: 8f95065cbd2d
Revises: ce963a9e2bce
Create Date: 2026-10-03 22:30:21.715178
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '8f95065cbd2d'
down_revision: str | None = 'ce963a9e2bce'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Короткие номера задач (решение №40): существующим — по порядку создания, начиная с 100001.
    op.execute("CREATE SEQUENCE task_number_seq START 100001")
    op.add_column('tasks', sa.Column('number', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE tasks t SET number = n.num
        FROM (SELECT id, nextval('task_number_seq') AS num FROM (SELECT id FROM tasks ORDER BY created_at, id) o) n
        WHERE t.id = n.id
    """)
    op.alter_column('tasks', 'number', nullable=False, server_default=sa.text("nextval('task_number_seq')"))
    op.execute("ALTER SEQUENCE task_number_seq OWNED BY tasks.number")
    op.create_unique_constraint('tasks_number_key', 'tasks', ['number'])


def downgrade() -> None:
    op.drop_constraint('tasks_number_key', 'tasks', type_='unique')
    op.drop_column('tasks', 'number')
