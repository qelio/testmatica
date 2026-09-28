"""Статус «снят администратором» у шаблонов КТП

Revision ID: ef21a728f7c1
Revises: 9e28421682d5
Create Date: 2026-09-28 09:19:08.894892
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'ef21a728f7c1'
down_revision: str | None = '9e28421682d5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint('status_valid', 'plan_templates', type_='check')
    op.create_check_constraint('status_valid', 'plan_templates', "status IN ('private', 'pending', 'published', 'rejected', 'removed')")


def downgrade() -> None:
    op.execute("UPDATE plan_templates SET status = 'private' WHERE status = 'removed'")
    op.drop_constraint('status_valid', 'plan_templates', type_='check')
    op.create_check_constraint('status_valid', 'plan_templates', "status IN ('private', 'pending', 'published', 'rejected')")
