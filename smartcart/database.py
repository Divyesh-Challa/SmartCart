"""
SmartCart Database Module - schema, migrations, real store data loading, and
crowdsourced price aggregation.

Store locations come from OpenStreetMap (smartcart/data/<region>_stores.json,
© OpenStreetMap contributors, ODbL). Shelf prices are never invented: they are
aggregated from rows in price_observations into the store_inventory cache.
"""

import datetime
import json
import sqlite3
import statistics
import tempfile
import math
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from smartcart.barcodes import normalize_barcode

DEFAULT_DB_FILE = "smartcart.db" if os.access(".", os.W_OK) else os.path.join(tempfile.gettempdir(), "smartcart.db")
DB_PATH = Path(os.environ.get("SMARTCART_DB_PATH", DEFAULT_DB_FILE))
DATA_DIR = Path(__file__).parent / "data"
DEFAULT_REGION = os.environ.get("SMARTCART_REGION", "edmonton")

# Observations older than this are ignored when computing a store's current price.
PRICE_OBSERVATION_WINDOW_DAYS = 30
PRICE_OBSERVATION_SOURCES = ("receipt", "manual", "flyer", "licensed_feed")

def extract_unit_size(text: str) -> str:
    """Extracts package / unit size (e.g. 1kg, 454g, 750g, 4L, 12-pack) from product title."""
    if not text:
        return "1 unit"
    t_lower = text.lower()
    if "per kg" in t_lower:
        return "1 kg"
    if "per lb" in t_lower:
        return "1 lb"
    patterns = [
        r"(\d+(?:\.\d+)?\s*-\s*(?:pack|pk)\b)",
        r"(\d+(?:\.\d+)?\s*(?:kg|g|lb|lbs|oz|ml|l|L)\b)",
        r"(\d+(?:\.\d+)?\s*(?:pack|pk|count|ct|bunch|cans?|bottles?|jug|bag|loaf)\b)",
        r"(bag of \d+)",
        r"(\d+\s*x\s*\d+\s*(?:g|ml|kg))",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return "1 unit"

def database_url() -> Optional[str]:
    """Postgres URL when configured; None means the local SQLite file at DB_PATH."""
    from smartcart.config import get_settings

    url = get_settings().database_url
    if url and url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        return url
    return None

def is_postgres() -> bool:
    return database_url() is not None

def sqlalchemy_url() -> str:
    url = database_url()
    if url is None:
        return f"sqlite:///{DB_PATH}"
    return re.sub(r"^postgres(ql)?(\+psycopg)?://", "postgresql+psycopg://", url)

def get_connection():
    """
    Returns a DB-API connection. SQLite connections are plain sqlite3 objects;
    Postgres connections are wrapped so the same SQL (qmark placeholders,
    case-insensitive LIKE, cursor.lastrowid) works unchanged.
    """
    url = database_url()
    if url is not None:
        return PostgresConnection(url)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

# Tables whose primary key is not an integer "id" column (no RETURNING id).
_TABLES_WITHOUT_ID = {"barcode_products", "sync_meta", "users", "alembic_version"}
_INSERT_TABLE_RE = re.compile(r"^\s*INSERT\s+INTO\s+(\w+)", re.IGNORECASE)
_LIKE_RE = re.compile(r"\bLIKE\b", re.IGNORECASE)

def translate_sql_for_postgres(sql: str) -> str:
    """Convert SQLite-flavoured SQL to psycopg: ? -> %s, % -> %%, LIKE -> ILIKE."""
    out = []
    in_quote = False
    for ch in sql:
        if ch == "'":
            in_quote = not in_quote
            out.append(ch)
        elif ch == "%":
            out.append("%%")
        elif ch == "?" and not in_quote:
            out.append("%s")
        else:
            out.append(ch)
    return _LIKE_RE.sub("ILIKE", "".join(out))

class PostgresCursor:
    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self.lastrowid: Optional[int] = None

    def execute(self, sql: str, params=()):
        translated = translate_sql_for_postgres(sql)
        m = _INSERT_TABLE_RE.match(sql)
        wants_id = bool(m) and m.group(1).lower() not in _TABLES_WITHOUT_ID and "RETURNING" not in sql.upper()
        if wants_id:
            translated = translated.rstrip().rstrip(";") + " RETURNING id"
        self._cur.execute(translated, tuple(params))
        if wants_id:
            row = self._cur.fetchone()
            self.lastrowid = row["id"] if row else None
        return self

    def executemany(self, sql: str, seq_of_params):
        self._cur.executemany(translate_sql_for_postgres(sql), [tuple(p) for p in seq_of_params])
        return self

    def executescript(self, script: str):
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur.fetchall())

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

class PostgresConnection:
    def __init__(self, url: str):
        import psycopg
        from psycopg.rows import dict_row

        self._conn = psycopg.connect(re.sub(r"^postgresql\+psycopg://", "postgresql://", url), row_factory=dict_row)

    def cursor(self) -> PostgresCursor:
        return PostgresCursor(self._conn.cursor())

    def execute(self, sql: str, params=()) -> PostgresCursor:
        return self.cursor().execute(sql, params)

    def executemany(self, sql: str, seq_of_params) -> PostgresCursor:
        return self.cursor().executemany(sql, seq_of_params)

    def executescript(self, script: str) -> PostgresCursor:
        return self.cursor().executescript(script)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

def init_db() -> None:
    """Bring the schema up to date by running Alembic migrations."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url().replace("%", "%%"))
    command.upgrade(cfg, "head")

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

# Generic catalog of staple products the basket optimizer can match against.
# These are product definitions only; prices come from price_observations.
PRODUCT_CATALOG = [
    ("Boneless Skinless Chicken Breasts", "Meat", "Generic", 1.0, "kg", "weight_100g", 10.0, "chicken breast, chicken breasts, chicken cutlets"),
    ("Boneless Skinless Chicken Thighs", "Meat", "Generic", 1.0, "kg", "weight_100g", 10.0, "chicken thighs, chicken thigh, chicken"),
    ("Lean Ground Beef", "Meat", "Generic", 1.0, "kg", "weight_100g", 10.0, "ground beef, minced beef, beef"),
    ("Fresh Atlantic Salmon Fillets", "Seafood", "Generic", 500.0, "g", "weight_100g", 5.0, "salmon, salmon fillet, fish"),
    ("2% Partly Skimmed Milk", "Dairy", "Dairyland", 4.0, "L", "volume_100ml", 40.0, "milk, 2% milk, cow milk"),
    ("Large Grade A White Eggs (12-pack)", "Dairy", "Generic", 12.0, "unit", "unit", 12.0, "eggs, egg, large eggs, dozen eggs"),
    ("Large Grade A White Eggs (30-pack)", "Dairy", "Generic", 30.0, "unit", "unit", 30.0, "eggs, egg, flat eggs, 30 eggs"),
    ("Salted Butter", "Dairy", "Generic", 454.0, "g", "weight_100g", 4.54, "butter, salted butter, baking butter"),
    ("Greek Yogurt Plain 0%", "Dairy", "Oikos", 750.0, "g", "weight_100g", 7.5, "greek yogurt, yogurt, plain yogurt"),
    ("Cheddar Cheese Block", "Dairy", "Kraft / Black Diamond", 400.0, "g", "weight_100g", 4.0, "cheddar cheese, cheese, cheese block"),
    ("Heavy Whipping Cream 33%", "Dairy", "Dairyland", 500.0, "ml", "volume_100ml", 5.0, "heavy cream, whipping cream, 35% cream"),
    ("Bananas", "Produce", "Cavendish", 1.0, "kg", "weight_100g", 10.0, "banana, bananas, fresh bananas"),
    ("Avocados (Bag of 5)", "Produce", "Generic", 5.0, "unit", "unit", 5.0, "avocado, avocados, ripe avos, avo"),
    ("Pineapple", "Produce", "Del Monte", 1.0, "unit", "unit", 1.0, "pineapple, pineapples, fresh pineapple"),
    ("Yellow Onions (3 lb bag)", "Produce", "Generic", 1.36, "kg", "weight_100g", 13.6, "onions, onion, yellow onion"),
    ("Baby Spinach", "Produce", "Organic Girl", 312.0, "g", "weight_100g", 3.12, "spinach, baby spinach, greens"),
    ("Garlic (3 pack)", "Produce", "Generic", 3.0, "unit", "unit", 3.0, "garlic, fresh garlic, garlic cloves"),
    ("Canned Crushed Tomatoes", "Pantry", "Unico", 796.0, "ml", "volume_100ml", 7.96, "canned tomatoes, crushed tomatoes, diced tomatoes, tomato sauce"),
    ("Garam Masala", "Pantry", "Suraj", 100.0, "g", "weight_100g", 1.0, "garam masala, curry powder, indian spices"),
    ("Long Grain Basmati Rice", "Pantry", "Tilda / Royal", 4.54, "kg", "weight_100g", 45.4, "basmati rice, rice, white rice"),
    ("Pasta Sauce (Marinara)", "Pantry", "Classico", 650.0, "ml", "volume_100ml", 6.5, "pasta sauce, marinara, spaghetti sauce"),
    ("Dry Spaghetti", "Pantry", "Barilla", 900.0, "g", "weight_100g", 9.0, "spaghetti, pasta, noodles"),
    ("White Sliced Sandwich Bread", "Bakery", "Wonder / D'Italiano", 675.0, "g", "weight_100g", 6.75, "bread, sliced bread, sandwich bread"),
    ("Extra Virgin Olive Oil", "Pantry", "Bertolli", 1.0, "L", "volume_100ml", 10.0, "olive oil, evoo, cooking oil"),
]

def seed_product_catalog(conn) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM products")
    if cursor.fetchone()["count"] == 0:
        cursor.executemany("""
        INSERT INTO products (name, category, brand, package_quantity, package_unit, standard_unit_type, normalized_amount, aliases)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, PRODUCT_CATALOG)
    conn.commit()

def load_real_stores(conn, region: str = DEFAULT_REGION) -> int:
    """
    Upsert stores from the OpenStreetMap export for a region, keyed on osm_id.
    Returns the number of stores loaded.
    """
    path = DATA_DIR / f"{region}_stores.json"
    payload = json.loads(path.read_text())
    cursor = conn.cursor()
    rows = [
        (
            st["osm_id"], st["name"], st["banner"], st["address"], st["city"], st["province"],
            st["postal_code"], st["latitude"], st["longitude"], st["requires_membership"],
            st.get("opening_hours"), st.get("website"), "openstreetmap", payload["fetched_at"],
        )
        for st in payload["stores"]
    ]
    cursor.executemany("""
        INSERT INTO stores (
            osm_id, name, banner, address, city, province, postal_code, latitude, longitude,
            requires_membership, opening_hours, website, source, data_updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(osm_id) DO UPDATE SET
            name = excluded.name,
            banner = excluded.banner,
            address = excluded.address,
            city = excluded.city,
            province = excluded.province,
            postal_code = excluded.postal_code,
            latitude = excluded.latitude,
            longitude = excluded.longitude,
            requires_membership = excluded.requires_membership,
            opening_hours = excluded.opening_hours,
            website = excluded.website,
            source = excluded.source,
            data_updated_at = excluded.data_updated_at
    """, rows)
    conn.commit()
    return len(rows)

def purge_unsourced_data(conn) -> Dict[str, int]:
    """
    Remove rows that have no real-world source: generated stores (no osm_id),
    generated inventory prices (not derived from observations), and the
    demo flyers/recipes/receipts/alerts/barcode prices from earlier versions.
    """
    cursor = conn.cursor()
    removed = {}
    statements = {
        "store_inventory": "DELETE FROM store_inventory WHERE source IS NULL OR store_id IN (SELECT id FROM stores WHERE osm_id IS NULL)",
        "price_observations": "DELETE FROM price_observations WHERE store_id IN (SELECT id FROM stores WHERE osm_id IS NULL)",
        "stores": "DELETE FROM stores WHERE osm_id IS NULL",
        "flyer_recipe_ingredients": "DELETE FROM flyer_recipe_ingredients",
        "flyer_recipes": "DELETE FROM flyer_recipes",
        "flyer_deals": "DELETE FROM flyer_deals",
        "flyers": "DELETE FROM flyers",
        "receipts": "DELETE FROM receipts",
        "sale_alerts": "DELETE FROM sale_alerts",
        "barcode_products": "DELETE FROM barcode_products",
    }
    for table, sql in statements.items():
        cursor.execute(sql)
        removed[table] = cursor.rowcount
    cursor.execute("DROP TABLE IF EXISTS test")
    conn.commit()
    return removed

def record_price_observation(
    conn,
    store_id: int,
    price: float,
    source: str,
    observed_at: Optional[str] = None,
    product_id: Optional[int] = None,
    upc: Optional[str] = None,
    raw_item_name: Optional[str] = None,
    is_sale: bool = False,
    submitted_by: Optional[str] = None,
    photo_key: Optional[str] = None,
    trust_score: float = 0.5,
) -> int:
    if source not in PRICE_OBSERVATION_SOURCES:
        raise ValueError(f"Unknown price source: {source}")
    if price <= 0:
        raise ValueError("Price must be positive")
    if product_id is None and not upc:
        raise ValueError("A price observation needs a product_id or a UPC")
    observed_at = observed_at or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    upc = normalize_barcode(upc) or None if upc else None
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO price_observations (
            store_id, product_id, upc, raw_item_name, price, is_sale, source,
            observed_at, submitted_by, photo_key, trust_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        store_id, product_id, upc, raw_item_name, round(price, 2), 1 if is_sale else 0, source,
        observed_at, submitted_by, photo_key, trust_score,
    ))
    conn.commit()
    return cursor.lastrowid

def refresh_inventory_from_observations(
    conn,
    window_days: int = PRICE_OBSERVATION_WINDOW_DAYS,
    store_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> int:
    """
    Rebuild the store_inventory price cache from accepted observations within
    the window: one row per (store, product) at the median observed price.
    Store/product pairs with no recent observations get no row, so the
    optimizer treats them as unknown rather than guessing.

    Pass store_id and product_id to rebuild just that one pair.
    """
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=window_days)).isoformat(timespec="seconds")
    pair_filter, pair_params = "", ()
    if store_id is not None and product_id is not None:
        pair_filter, pair_params = " AND o.store_id = ? AND o.product_id = ?", (store_id, product_id)

    cursor = conn.cursor()
    cursor.execute("""
        SELECT o.store_id, o.product_id, o.price, o.observed_at, o.source, p.normalized_amount
        FROM price_observations o
        JOIN products p ON p.id = o.product_id
        WHERE o.status = 'accepted' AND o.product_id IS NOT NULL AND o.observed_at >= ?
    """ + pair_filter, (cutoff,) + pair_params)

    grouped: Dict[tuple, List[Dict[str, Any]]] = {}
    for row in cursor.fetchall():
        grouped.setdefault((row["store_id"], row["product_id"]), []).append(dict(row))

    rows = []
    for (s_id, p_id), obs in grouped.items():
        price = round(statistics.median(o["price"] for o in obs), 2)
        latest = max(obs, key=lambda o: o["observed_at"])
        sources = {o["source"] for o in obs}
        confidence = round(min(0.95, 0.5 + 0.1 * len(obs)), 2)
        rows.append((
            s_id, p_id, price, round(price / latest["normalized_amount"], 4), 1,
            confidence, ",".join(sorted(sources)), len(obs), latest["observed_at"],
        ))

    if pair_params:
        cursor.execute("DELETE FROM store_inventory WHERE store_id = ? AND product_id = ?", pair_params)
    else:
        cursor.execute("DELETE FROM store_inventory")
    cursor.executemany("""
        INSERT INTO store_inventory (
            store_id, product_id, price, unit_price, in_stock,
            confidence_score, source, observation_count, last_observed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return len(rows)

def bootstrap_database(region: str = DEFAULT_REGION) -> Dict[str, Any]:
    """Create the schema, load the product catalog and real stores, and rebuild prices."""
    init_db()
    conn = get_connection()
    try:
        seed_product_catalog(conn)
        stores = load_real_stores(conn, region)
        priced = refresh_inventory_from_observations(conn)
    finally:
        conn.close()
    return {"region": region, "stores_loaded": stores, "inventory_rows": priced}

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialise the SmartCart database.")
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument(
        "--purge-unsourced",
        action="store_true",
        help="One-time cleanup: delete generated stores, prices and demo content from older versions.",
    )
    args = parser.parse_args()

    if args.purge_unsourced:
        init_db()
        conn = get_connection()
        print("Purged:", purge_unsourced_data(conn))
        conn.close()
    print(bootstrap_database(args.region))
