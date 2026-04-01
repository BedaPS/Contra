"""add_app_settings_table

Revision ID: b5e9a2f3c180
Revises: a3f8c2e1d097
Create Date: 2026-04-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5e9a2f3c180"
down_revision: Union[str, Sequence[str], None] = "a3f8c2e1d097"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", sa.Text, nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
