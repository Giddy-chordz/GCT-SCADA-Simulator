"""Add manual_override column to equipments

Revision ID: a1b2c3d4e5f6
Revises: 6683b13be94e
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '6683b13be94e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add manual_override boolean column to equipments.

    Defaults to False so all existing rows are unaffected — no existing
    operator command is retroactively treated as a manual override.
    """
    op.add_column(
        'equipments',
        sa.Column(
            'manual_override',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Remove manual_override column from equipments."""
    op.drop_column('equipments', 'manual_override')
