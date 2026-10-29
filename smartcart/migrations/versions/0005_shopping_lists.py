"""Shopping lists synced to accounts.

One row per user holding the list as JSON, so a list follows the shopper
across devices. Row-level security is enabled like every other table (see 0004).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shopping_lists",
        sa.Column("user_id", sa.Text, primary_key=True),
        sa.Column("items_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.Text, nullable=False),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE public."shopping_lists" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("shopping_lists")
