"""Чаты поддержки (спор по отзыву)

Revision ID: 5cae01e23d9e
Revises: 71a9de2f2ca9
Create Date: 2026-09-26 10:21:39.992634
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '5cae01e23d9e'
down_revision: str | None = '71a9de2f2ca9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint('kind_valid', 'conversations', type_='check')
    op.drop_constraint('ref_valid', 'conversations', type_='check')
    op.create_check_constraint('kind_valid', 'conversations', "kind IN ('direct', 'group', 'deal', 'support')")
    op.create_check_constraint(
        'ref_valid', 'conversations',
        "(kind = 'group' AND group_id IS NOT NULL) OR (kind = 'direct' AND pair_key IS NOT NULL) OR kind IN ('deal', 'support')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM conversations WHERE kind = 'support'")
    op.drop_constraint('ref_valid', 'conversations', type_='check')
    op.drop_constraint('kind_valid', 'conversations', type_='check')
    op.create_check_constraint('kind_valid', 'conversations', "kind IN ('direct', 'group', 'deal')")
    op.create_check_constraint(
        'ref_valid', 'conversations',
        "(kind = 'group' AND group_id IS NOT NULL) OR (kind = 'direct' AND pair_key IS NOT NULL) OR kind = 'deal'",
    )
