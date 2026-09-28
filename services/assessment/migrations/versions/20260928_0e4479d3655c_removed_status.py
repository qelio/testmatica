"""Статус «снята администратором» у задач

Revision ID: 0e4479d3655c
Revises: 91424200c2e7
Create Date: 2026-09-28 09:16:53.774259
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0e4479d3655c'
down_revision: str | None = '91424200c2e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint('status_valid', 'tasks', type_='check')
    op.create_check_constraint('status_valid', 'tasks', "status IN ('private', 'pending', 'published', 'rejected', 'removed')")


def downgrade() -> None:
    op.execute("UPDATE tasks SET status = 'private' WHERE status = 'removed'")
    op.drop_constraint('status_valid', 'tasks', type_='check')
    op.create_check_constraint('status_valid', 'tasks', "status IN ('private', 'pending', 'published', 'rejected')")
