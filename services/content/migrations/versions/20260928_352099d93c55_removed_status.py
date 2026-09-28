"""Статус «снят администратором» у курсов

Revision ID: 352099d93c55
Revises: b5eea1e4d610
Create Date: 2026-09-28 09:15:07.710111
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '352099d93c55'
down_revision: str | None = 'b5eea1e4d610'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint('status_valid', 'nodes', type_='check')
    op.create_check_constraint('status_valid', 'nodes', "status IS NULL OR status IN ('private', 'pending', 'published', 'rejected', 'removed')")


def downgrade() -> None:
    op.execute("UPDATE nodes SET status = 'private' WHERE status = 'removed'")
    op.drop_constraint('status_valid', 'nodes', type_='check')
    op.create_check_constraint('status_valid', 'nodes', "status IS NULL OR status IN ('private', 'pending', 'published', 'rejected')")
