"""Baseline schema.

Creates every table SmartCart uses. It is safe to run against databases created
by the pre-Alembic init_db(): existing tables are kept and only missing tables,
columns and indexes are added.

Timestamps that are compared as strings (observed_at, valid_from/valid_to,
synced_at...) are stored as ISO-8601 TEXT on both SQLite and Postgres.

Revision ID: 0001
Revises:
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _pk():
    return sa.Column("id", sa.Integer, primary_key=True, autoincrement=True)


def _created_at():
    return sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp())


TABLES = {
    "stores": lambda: [
        _pk(),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("banner", sa.Text, nullable=False),
        sa.Column("address", sa.Text, nullable=False),
        sa.Column("city", sa.Text, server_default="Edmonton"),
        sa.Column("postal_code", sa.Text),
        sa.Column("quadrant", sa.Text),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("requires_membership", sa.Integer, server_default="0"),
        sa.Column("osm_id", sa.Text),
        sa.Column("province", sa.Text),
        sa.Column("opening_hours", sa.Text),
        sa.Column("website", sa.Text),
        sa.Column("source", sa.Text),
        sa.Column("verified", sa.Integer, server_default="0"),
        sa.Column("data_updated_at", sa.Text),
    ],
    "products": lambda: [
        _pk(),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("brand", sa.Text),
        sa.Column("package_quantity", sa.Float, nullable=False),
        sa.Column("package_unit", sa.Text, nullable=False),
        sa.Column("standard_unit_type", sa.Text, nullable=False),
        sa.Column("normalized_amount", sa.Float, nullable=False),
        sa.Column("aliases", sa.Text),
    ],
    "store_inventory": lambda: [
        _pk(),
        sa.Column("store_id", sa.Integer, sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("unit_price", sa.Float, nullable=False),
        sa.Column("in_stock", sa.Integer, server_default="1"),
        sa.Column("confidence_score", sa.Float, server_default="0.95"),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("source", sa.Text),
        sa.Column("observation_count", sa.Integer, server_default="0"),
        sa.Column("last_observed_at", sa.Text),
    ],
    "price_observations": lambda: [
        _pk(),
        sa.Column("store_id", sa.Integer, sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id")),
        sa.Column("upc", sa.Text),
        sa.Column("raw_item_name", sa.Text),
        sa.Column("price", sa.Float, sa.CheckConstraint("price > 0"), nullable=False),
        sa.Column("is_sale", sa.Integer, server_default="0"),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("observed_at", sa.Text, nullable=False),
        sa.Column("submitted_by", sa.Text),
        sa.Column("photo_key", sa.Text),
        sa.Column("trust_score", sa.Float, server_default="0.5"),
        sa.Column("status", sa.Text, server_default="accepted"),
        _created_at(),
    ],
    "flyers": lambda: [
        _pk(),
        sa.Column("banner", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("total_pages", sa.Integer, server_default="6"),
        sa.Column("valid_from", sa.Text, nullable=False),
        sa.Column("valid_to", sa.Text, nullable=False),
        sa.Column("badge_text", sa.Text),
        sa.Column("color_theme", sa.Text),
    ],
    "flyer_deals": lambda: [
        _pk(),
        sa.Column("flyer_id", sa.Integer, sa.ForeignKey("flyers.id"), nullable=False),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id")),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("page_number", sa.Integer, server_default="1"),
        sa.Column("original_price", sa.Float),
        sa.Column("sale_price", sa.Float, nullable=False),
        sa.Column("unit_sale_price", sa.Text),
        sa.Column("discount_text", sa.Text),
        sa.Column("is_front_page", sa.Integer, server_default="0"),
        sa.Column("store_name", sa.Text),
        sa.Column("unit_size", sa.Text),
        sa.Column("valid_until", sa.Text),
        sa.Column("item_name", sa.Text),
    ],
    "custom_flyer_pages": lambda: [
        _pk(),
        sa.Column("banner", sa.Text, nullable=False),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("image_url", sa.Text, nullable=False),
        sa.Column("title", sa.Text),
        _created_at(),
        sa.UniqueConstraint("banner", "page_number"),
    ],
    "flyer_recipes": lambda: [
        _pk(),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("banner", sa.Text, nullable=False),
        sa.Column("cuisine", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("prep_time_minutes", sa.Integer, nullable=False),
        sa.Column("servings", sa.Integer, nullable=False),
        sa.Column("difficulty", sa.Text, server_default="Easy"),
        sa.Column("cost_per_serving", sa.Float, nullable=False),
        sa.Column("total_sale_cost", sa.Float, nullable=False),
        sa.Column("total_regular_cost", sa.Float, nullable=False),
        sa.Column("savings_amount", sa.Float, nullable=False),
        sa.Column("savings_percent", sa.Integer, nullable=False),
        sa.Column("badge_text", sa.Text),
        sa.Column("instructions_json", sa.Text),
        _created_at(),
    ],
    "flyer_recipe_ingredients": lambda: [
        _pk(),
        sa.Column("recipe_id", sa.Integer, sa.ForeignKey("flyer_recipes.id"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("brand", sa.Text),
        sa.Column("package_size", sa.Text),
        sa.Column("category", sa.Text),
        sa.Column("sale_price", sa.Float, nullable=False),
        sa.Column("regular_price", sa.Float, nullable=False),
        sa.Column("savings", sa.Float, nullable=False),
        sa.Column("quantity", sa.Float, server_default="1.0"),
        sa.Column("unit", sa.Text, server_default="unit"),
    ],
    "recipe_requests": lambda: [
        _pk(),
        sa.Column("dish_name", sa.Text, nullable=False),
        sa.Column("cuisine_preference", sa.Text),
        sa.Column("dietary_notes", sa.Text),
        sa.Column("user_email", sa.Text),
        _created_at(),
    ],
    "barcode_products": lambda: [
        sa.Column("barcode", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("brand", sa.Text),
        sa.Column("package_size", sa.Text),
        sa.Column("category", sa.Text),
        sa.Column("sale_price", sa.Float, nullable=False),
        sa.Column("regular_price", sa.Float, nullable=False),
        sa.Column("banner", sa.Text),
        sa.Column("is_on_sale", sa.Integer, server_default="1"),
        sa.Column("calories", sa.Integer),
        sa.Column("protein_g", sa.Float),
        sa.Column("carbs_g", sa.Float),
        sa.Column("fat_g", sa.Float),
        sa.Column("fiber_g", sa.Float),
        sa.Column("sodium_mg", sa.Float),
        sa.Column("nutri_score", sa.Text, server_default="A"),
        sa.Column("ingredients_text", sa.Text),
        sa.Column("image_url", sa.Text),
    ],
    "receipts": lambda: [
        _pk(),
        sa.Column("store_name", sa.Text, nullable=False),
        sa.Column("trip_date", sa.Text, nullable=False),
        sa.Column("amount_spent", sa.Float, nullable=False),
        sa.Column("regular_amount", sa.Float, nullable=False),
        sa.Column("amount_saved", sa.Float, nullable=False),
        sa.Column("savings_percent", sa.Integer, nullable=False),
        sa.Column("items_count", sa.Integer, server_default="0"),
        sa.Column("category", sa.Text, server_default="Groceries"),
        sa.Column("notes", sa.Text),
        _created_at(),
    ],
    "sale_alerts": lambda: [
        _pk(),
        sa.Column("product_name", sa.Text, nullable=False),
        sa.Column("category", sa.Text, server_default="Pantry"),
        sa.Column("target_price", sa.Float),
        sa.Column("current_sale_price", sa.Float),
        sa.Column("regular_price", sa.Float),
        sa.Column("banner", sa.Text),
        sa.Column("is_on_sale", sa.Integer, server_default="1"),
        _created_at(),
    ],
    "sync_history": lambda: [
        _pk(),
        sa.Column("synced_at", sa.Text, nullable=False),
        sa.Column("stores_count", sa.Integer, nullable=False),
        sa.Column("inventory_rows_count", sa.Integer, nullable=False),
        sa.Column("flyer_deals_count", sa.Integer, nullable=False),
        sa.Column("gas_price_ab", sa.Float, nullable=False),
        sa.Column("gas_price_bc", sa.Float, nullable=False),
        sa.Column("flyer_cycle_label", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("details", sa.Text),
        sa.Column("next_sync_at", sa.Text, nullable=False),
    ],
    "sync_meta": lambda: [
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    ],
}

INDEXES = [
    ("idx_inventory_store", "store_inventory", ["store_id"], False),
    ("idx_inventory_product", "store_inventory", ["product_id"], False),
    ("idx_inventory_prod_store", "store_inventory", ["product_id", "store_id"], False),
    ("idx_stores_lat_lon", "stores", ["latitude", "longitude"], False),
    ("idx_stores_osm_id", "stores", ["osm_id"], True),
    ("idx_products_name", "products", ["name"], False),
    ("idx_flyer_deals_flyer", "flyer_deals", ["flyer_id"], False),
    ("idx_flyer_deals_page", "flyer_deals", ["page_number"], False),
    ("idx_price_obs_store_product", "price_observations", ["store_id", "product_id", "observed_at"], False),
    ("idx_price_obs_upc", "price_observations", ["upc"], False),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for name, columns in TABLES.items():
        if name not in existing_tables:
            op.create_table(name, *columns())
            continue
        # Legacy database: add any columns introduced after the table was created.
        present = {c["name"] for c in inspector.get_columns(name)}
        for col in columns():
            if isinstance(col, sa.Column) and col.name not in present:
                default = col.server_default.arg if col.server_default is not None else None
                op.add_column(name, sa.Column(col.name, col.type, server_default=default))

    for table in ("test", "categories"):
        if table in existing_tables:
            op.drop_table(table)

    inspector = sa.inspect(bind)
    for index_name, table, cols, unique in INDEXES:
        existing = {ix["name"] for ix in inspector.get_indexes(table)}
        if index_name not in existing:
            op.create_index(index_name, table, cols, unique=unique)


def downgrade() -> None:
    for name in reversed(list(TABLES)):
        op.drop_table(name)
