"""barcode_products becomes a product-info cache with no invented prices.

Prices for scanned items now come from price_observations; the legacy price
columns become nullable and provenance columns are added.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("barcode_products") as batch:
        batch.alter_column("sale_price", existing_type=sa.Float, nullable=True)
        batch.alter_column("regular_price", existing_type=sa.Float, nullable=True)
        batch.alter_column("is_on_sale", existing_type=sa.Integer, server_default=None)
        batch.alter_column("nutri_score", existing_type=sa.Text, server_default=None)
        batch.add_column(sa.Column("source", sa.Text))
        batch.add_column(sa.Column("fetched_at", sa.Text))


def downgrade() -> None:
    with op.batch_alter_table("barcode_products") as batch:
        batch.drop_column("fetched_at")
        batch.drop_column("source")
