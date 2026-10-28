"""User accounts and per-user ownership.

Adds a users table keyed by the Supabase auth user id (a UUID string) and a
user_id owner column on every table that holds personal data.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

OWNED_TABLES = ("receipts", "sale_alerts", "recipe_requests")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("email", sa.Text),
        sa.Column("display_name", sa.Text),
        sa.Column("plan", sa.Text, nullable=False, server_default="free"),
        sa.Column("trust_score", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("is_admin", sa.Integer, nullable=False, server_default="0"),
        sa.Column("home_postal_code", sa.Text),
        sa.Column("marketing_opt_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("marketing_opt_in_at", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("last_seen_at", sa.Text),
    )
    for table in OWNED_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("user_id", sa.Text))
        op.create_index(f"idx_{table}_user", table, ["user_id"])
    op.create_index("idx_price_obs_submitted_by", "price_observations", ["submitted_by", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_price_obs_submitted_by", "price_observations")
    for table in OWNED_TABLES:
        op.drop_index(f"idx_{table}_user", table)
        with op.batch_alter_table(table) as batch:
            batch.drop_column("user_id")
    op.drop_table("users")
