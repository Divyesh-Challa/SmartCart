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
import math
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

DEFAULT_DB_FILE = "smartcart.db" if os.access(".", os.W_OK) else "/tmp/smartcart.db"
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

def get_connection():
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS stores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        banner TEXT NOT NULL,
        address TEXT NOT NULL,
        city TEXT DEFAULT 'Edmonton',
        postal_code TEXT,
        quadrant TEXT,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        requires_membership INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        brand TEXT,
        package_quantity REAL NOT NULL,
        package_unit TEXT NOT NULL,
        standard_unit_type TEXT NOT NULL,
        normalized_amount REAL NOT NULL,
        aliases TEXT
    );

    CREATE TABLE IF NOT EXISTS store_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        price REAL NOT NULL,
        unit_price REAL NOT NULL,
        in_stock INTEGER DEFAULT 1,
        confidence_score REAL DEFAULT 0.95,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (store_id) REFERENCES stores(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );

    CREATE TABLE IF NOT EXISTS flyers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        banner TEXT NOT NULL,
        title TEXT NOT NULL,
        total_pages INTEGER DEFAULT 6,
        valid_from TEXT NOT NULL,
        valid_to TEXT NOT NULL,
        badge_text TEXT,
        color_theme TEXT
    );

    CREATE TABLE IF NOT EXISTS flyer_deals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        flyer_id INTEGER NOT NULL,
        product_id INTEGER,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        page_number INTEGER DEFAULT 1,
        original_price REAL,
        sale_price REAL NOT NULL,
        unit_sale_price TEXT,
        discount_text TEXT,
        is_front_page INTEGER DEFAULT 0,
        store_name TEXT,
        unit_size TEXT,
        valid_until TEXT,
        FOREIGN KEY (flyer_id) REFERENCES flyers(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );

    -- Schema migration for structured flyer deals
    PRAGMA table_info(flyer_deals);


    CREATE INDEX IF NOT EXISTS idx_inventory_store ON store_inventory(store_id);
    CREATE INDEX IF NOT EXISTS idx_inventory_product ON store_inventory(product_id);
    CREATE INDEX IF NOT EXISTS idx_inventory_prod_store ON store_inventory(product_id, store_id);
    CREATE INDEX IF NOT EXISTS idx_stores_lat_lon ON stores(latitude, longitude);
    CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
    CREATE INDEX IF NOT EXISTS idx_flyer_deals_flyer ON flyer_deals(flyer_id);
    CREATE INDEX IF NOT EXISTS idx_flyer_deals_page ON flyer_deals(page_number);
    CREATE TABLE IF NOT EXISTS custom_flyer_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        banner TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        image_url TEXT NOT NULL,
        title TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(banner, page_number)
    );

    CREATE TABLE IF NOT EXISTS flyer_recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        banner TEXT NOT NULL,
        cuisine TEXT NOT NULL,
        category TEXT NOT NULL,
        prep_time_minutes INTEGER NOT NULL,
        servings INTEGER NOT NULL,
        difficulty TEXT DEFAULT 'Easy',
        cost_per_serving REAL NOT NULL,
        total_sale_cost REAL NOT NULL,
        total_regular_cost REAL NOT NULL,
        savings_amount REAL NOT NULL,
        savings_percent INTEGER NOT NULL,
        badge_text TEXT,
        instructions_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS flyer_recipe_ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        brand TEXT,
        package_size TEXT,
        category TEXT,
        sale_price REAL NOT NULL,
        regular_price REAL NOT NULL,
        savings REAL NOT NULL,
        quantity REAL DEFAULT 1.0,
        unit TEXT DEFAULT 'unit',
        FOREIGN KEY (recipe_id) REFERENCES flyer_recipes(id)
    );

    CREATE TABLE IF NOT EXISTS recipe_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dish_name TEXT NOT NULL,
        cuisine_preference TEXT,
        dietary_notes TEXT,
        user_email TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS barcode_products (
        barcode TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        brand TEXT,
        package_size TEXT,
        category TEXT,
        sale_price REAL NOT NULL,
        regular_price REAL NOT NULL,
        banner TEXT,
        is_on_sale INTEGER DEFAULT 1,
        calories INTEGER,
        protein_g REAL,
        carbs_g REAL,
        fat_g REAL,
        fiber_g REAL,
        sodium_mg REAL,
        nutri_score TEXT DEFAULT 'A',
        ingredients_text TEXT,
        image_url TEXT
    );

    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_name TEXT NOT NULL,
        trip_date TEXT NOT NULL,
        amount_spent REAL NOT NULL,
        regular_amount REAL NOT NULL,
        amount_saved REAL NOT NULL,
        savings_percent INTEGER NOT NULL,
        items_count INTEGER DEFAULT 0,
        category TEXT DEFAULT 'Groceries',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS sale_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT NOT NULL,
        category TEXT DEFAULT 'Pantry',
        target_price REAL,
        current_sale_price REAL,
        regular_price REAL,
        banner TEXT,
        is_on_sale INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS price_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER NOT NULL,
        product_id INTEGER,
        upc TEXT,
        raw_item_name TEXT,
        price REAL NOT NULL CHECK (price > 0),
        is_sale INTEGER DEFAULT 0,
        source TEXT NOT NULL,
        observed_at TIMESTAMP NOT NULL,
        submitted_by TEXT,
        photo_key TEXT,
        trust_score REAL DEFAULT 0.5,
        status TEXT DEFAULT 'accepted',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (store_id) REFERENCES stores(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );
    CREATE INDEX IF NOT EXISTS idx_price_obs_store_product ON price_observations(store_id, product_id, observed_at);
    CREATE INDEX IF NOT EXISTS idx_price_obs_upc ON price_observations(upc);
    """)

    _add_missing_columns(cursor, "stores", {
        "osm_id": "TEXT",
        "province": "TEXT",
        "opening_hours": "TEXT",
        "website": "TEXT",
        "source": "TEXT",
        "verified": "INTEGER DEFAULT 0",
        "data_updated_at": "TEXT",
    })
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_stores_osm_id ON stores(osm_id)")

    _add_missing_columns(cursor, "store_inventory", {
        "source": "TEXT",
        "observation_count": "INTEGER DEFAULT 0",
        "last_observed_at": "TEXT",
    })

    # Dynamic migration for flyer_deals structured fields
    cursor.execute("PRAGMA table_info(flyer_deals)")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    for col_name in ["store_name", "item_name", "unit_size", "valid_until"]:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE flyer_deals ADD COLUMN {col_name} TEXT")
    
    cursor.execute("""
        UPDATE flyer_deals
        SET store_name = (SELECT f.banner FROM flyers f WHERE f.id = flyer_deals.flyer_id)
        WHERE store_name IS NULL
    """)
    cursor.execute("""
        UPDATE flyer_deals
        SET item_name = COALESCE(item_name, title)
        WHERE item_name IS NULL
    """)
    cursor.execute("""
        UPDATE flyer_deals
        SET valid_until = (SELECT f.valid_to FROM flyers f WHERE f.id = flyer_deals.flyer_id)
        WHERE valid_until IS NULL
    """)
    cursor.execute("""
        UPDATE flyer_deals
        SET unit_size = (SELECT printf('%g %s', p.package_quantity, p.package_unit) FROM products p WHERE p.id = flyer_deals.product_id)
        WHERE (unit_size IS NULL OR unit_size = '') AND product_id IS NOT NULL
    """)

    # Fill unit_size with extracted size from title when available
    cursor.execute("SELECT id, title, unit_size FROM flyer_deals")
    for r in cursor.fetchall():
        ext = extract_unit_size(r["title"])
        if ext and ext != "1 unit":
            cursor.execute("UPDATE flyer_deals SET unit_size = ? WHERE id = ?", (ext, r["id"]))
        elif not r["unit_size"]:
            cursor.execute("UPDATE flyer_deals SET unit_size = '1 unit' WHERE id = ?", (r["id"],))

    conn.commit()
    conn.close()

def _add_missing_columns(cursor, table: str, columns: Dict[str, str]) -> None:
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row["name"] for row in cursor.fetchall()}
    for name, ddl in columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

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

def refresh_inventory_from_observations(conn, window_days: int = PRICE_OBSERVATION_WINDOW_DAYS) -> int:
    """
    Rebuild the store_inventory price cache from accepted observations within
    the window: one row per (store, product) at the median observed price.
    Store/product pairs with no recent observations get no row, so the
    optimizer treats them as unknown rather than guessing.
    """
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=window_days)).isoformat(timespec="seconds")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT o.store_id, o.product_id, o.price, o.observed_at, o.source, p.normalized_amount
        FROM price_observations o
        JOIN products p ON p.id = o.product_id
        WHERE o.status = 'accepted' AND o.product_id IS NOT NULL AND o.observed_at >= ?
    """, (cutoff,))

    grouped: Dict[tuple, List[Dict[str, Any]]] = {}
    for row in cursor.fetchall():
        grouped.setdefault((row["store_id"], row["product_id"]), []).append(dict(row))

    rows = []
    for (store_id, product_id), obs in grouped.items():
        price = round(statistics.median(o["price"] for o in obs), 2)
        latest = max(obs, key=lambda o: o["observed_at"])
        sources = {o["source"] for o in obs}
        confidence = round(min(0.95, 0.5 + 0.1 * len(obs)), 2)
        rows.append((
            store_id, product_id, price, round(price / latest["normalized_amount"], 4), 1,
            confidence, ",".join(sorted(sources)), len(obs), latest["observed_at"],
        ))

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
