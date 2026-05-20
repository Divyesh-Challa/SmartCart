"""
SmartCart Database Module - Comprehensive Edmonton-wide Supermarkets and Complete Multi-Page Digital Flyers
"""

import sqlite3
import math
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_PATH = Path(os.environ.get("SMARTCART_DB_PATH", "/tmp/smartcart.db"))

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
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
        FOREIGN KEY (flyer_id) REFERENCES flyers(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );

    CREATE INDEX IF NOT EXISTS idx_inventory_store ON store_inventory(store_id);
    CREATE INDEX IF NOT EXISTS idx_inventory_product ON store_inventory(product_id);
    CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
    CREATE INDEX IF NOT EXISTS idx_flyer_deals_flyer ON flyer_deals(flyer_id);
    CREATE INDEX IF NOT EXISTS idx_flyer_deals_page ON flyer_deals(page_number);
    """)

    conn.commit()
    conn.close()

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

def seed_edmonton_data(force: bool = False):
    conn = get_connection()
    cursor = conn.cursor()

    if force:
        cursor.executescript("""
        DELETE FROM flyer_deals;
        DELETE FROM flyers;
        DELETE FROM store_inventory;
        DELETE FROM products;
        DELETE FROM stores;
        """)

    cursor.execute("SELECT COUNT(*) as count FROM stores")
    if cursor.fetchone()["count"] > 10 and not force:
        conn.close()
        return

    # 1. Edmonton-Wide Supermarkets
    stores = [
        ("Real Canadian Superstore - Kingsway", "Superstore", "1155 Kingsway NW", "T5G 3E8", "Central", 53.5606, -113.5137, 0),
        ("Safeway - Unity Square", "Safeway", "11210 104 Ave NW", "T5K 2X4", "Central", 53.5469, -113.5147, 0),
        ("No Frills - Old Strathcona", "No Frills", "10439 82 Ave NW", "T6E 2A1", "Central", 53.5186, -113.4988, 0),
        ("Save-On-Foods - 109 St", "Save-On-Foods", "10940 82 Ave NW", "T6G 0S6", "Central", 53.5181, -113.5123, 0),

        ("Real Canadian Superstore - South Common", "Superstore", "2018 99 St NW", "T6N 1J8", "South", 53.4508, -113.4883, 0),
        ("Walmart Supercentre - South Common", "Walmart", "2132 99 St NW", "T6N 1J8", "South", 53.4485, -113.4891, 0),
        ("Costco Wholesale - 91 St SW", "Costco", "2616 91 St SW", "T6X 1N2", "South", 53.4215, -113.4682, 1),
        ("No Frills - Mill Woods", "No Frills", "28 Ave NW & 66 St", "T6K 4A2", "South", 53.4592, -113.4328, 0),
        ("Safeway - Southgate Centre", "Safeway", "5105 111 St NW", "T6H 4M6", "South", 53.4862, -113.5178, 0),

        ("Real Canadian Superstore - West Edmonton", "Superstore", "17303 100 Ave NW", "T5S 2P4", "West", 53.5395, -113.6212, 0),
        ("Walmart Supercentre - West Edmonton Mall", "Walmart", "8882 170 St NW", "T5T 4M2", "West", 53.5225, -113.6241, 0),
        ("No Frills - Callingwood", "No Frills", "6655 178 St NW", "T5T 4J5", "West", 53.5042, -113.6289, 0),
        ("Costco Wholesale - Winterburn (149 St)", "Costco", "12450 149 St NW", "T5V 1G9", "West", 53.5788, -113.5791, 1),
        ("Save-On-Foods - Hamptons", "Save-On-Foods", "6260 199 St NW", "T5T 2K4", "West", 53.4975, -113.6621, 0),

        ("Walmart Supercentre - Capilano", "Walmart", "5004 98 Ave NW", "T6A 0A1", "East", 53.5358, -113.4182, 0),
        ("Real Canadian Superstore - Clareview", "Superstore", "5003 137 Ave NW", "T5Y 2W6", "East", 53.6025, -113.4152, 0),
        ("Walmart Supercentre - Clareview", "Walmart", "4015 137 Ave NW", "T5Y 3C5", "East", 53.5992, -113.3982, 0),
        ("Safeway - Capilano", "Safeway", "5004 98 Ave NW", "T6A 0A1", "East", 53.5361, -113.4175, 0),

        ("Walmart Supercentre - Northland", "Walmart", "13703 40 St NW", "T5Y 3B5", "North", 53.5985, -113.3985, 0),
        ("Safeway - Castle Downs", "Safeway", "11804 145 Ave NW", "T5X 2E3", "North", 53.6075, -113.5248, 0),
        ("Costco Wholesale - St. Albert", "Costco", "1075 St Albert Trail", "T8N 4K6", "Region", 53.6621, -113.6421, 1),
        ("Save-On-Foods - Baseline (Sherwood Park)", "Save-On-Foods", "4005 Baseline Rd", "T8H 1N5", "Region", 53.5362, -113.3142, 0)
    ]

    cursor.executemany("""
    INSERT INTO stores (name, banner, address, postal_code, quadrant, latitude, longitude, requires_membership)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, stores)

    # 2. Products Catalog
    products = [
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

    cursor.executemany("""
    INSERT INTO products (name, category, brand, package_quantity, package_unit, standard_unit_type, normalized_amount, aliases)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, products)

    banner_multipliers = {
        "No Frills": 0.92,
        "Walmart": 0.94,
        "Superstore": 1.00,
        "Save-On-Foods": 1.08,
        "Safeway": 1.15,
        "Costco": 0.86,
    }

    base_prices = {
        1: 13.99, 2: 11.99, 3: 12.50, 4: 14.99, 5: 5.79, 6: 4.19, 7: 9.49, 8: 5.49,
        9: 6.29, 10: 5.99, 11: 3.99, 12: 1.74, 13: 4.99, 14: 3.49, 15: 3.99, 16: 4.99,
        17: 1.49, 18: 2.49, 19: 2.99, 20: 14.99, 21: 3.49, 22: 3.29, 23: 3.19, 24: 13.99
    }

    cursor.execute("SELECT id, normalized_amount FROM products")
    prod_norms = {row["id"]: row["normalized_amount"] for row in cursor.fetchall()}

    cursor.execute("SELECT id, banner FROM stores")
    all_stores = [dict(row) for row in cursor.fetchall()]

    inventory_rows = []
    for s in all_stores:
        s_id = s["id"]
        mult = banner_multipliers.get(s["banner"], 1.0)
        for p_id, base_p in base_prices.items():
            norm_amt = prod_norms[p_id]
            price = round(base_p * mult, 2)
            unit_price = round(price / norm_amt, 4)
            in_stock = 0 if (s_id + p_id) % 37 == 0 else 1
            inventory_rows.append((s_id, p_id, price, unit_price, in_stock))

    cursor.executemany("""
    INSERT INTO store_inventory (store_id, product_id, price, unit_price, in_stock)
    VALUES (?, ?, ?, ?, ?)
    """, inventory_rows)

    # 3. Seed Flyers
    flyers_data = [
        ("No Frills", "Won't Be Beat Weekly Circular", 6, "2026-10-01", "2026-10-07", "Haul of the Week", "bg-yellow-400 text-yellow-950"),
        ("Walmart", "Rollback Savings Event Circular", 6, "2026-10-01", "2026-10-07", "Save Money. Live Better.", "bg-blue-600 text-white"),
        ("Superstore", "President's Choice & More for Less", 6, "2026-10-01", "2026-10-07", "Optimum Deals", "bg-amber-500 text-white"),
        ("Safeway", "Taste of Fall Weekly Deals Circular", 5, "2026-10-01", "2026-10-07", "Scene+ Rewards", "bg-rose-600 text-white"),
        ("Save-On-Foods", "Western Family & Darrell's Deals", 5, "2026-10-01", "2026-10-07", "Darrell's Deal", "bg-emerald-600 text-white"),
        ("Costco", "Warehouse Instant Savings Book", 4, "2026-09-28", "2026-10-11", "Member Exclusive", "bg-indigo-600 text-white"),
    ]

    cursor.executemany("""
    INSERT INTO flyers (banner, title, total_pages, valid_from, valid_to, badge_text, color_theme)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, flyers_data)

    cursor.execute("SELECT id, banner FROM flyers")
    flyer_map = {row["banner"]: row["id"] for row in cursor.fetchall()}

    # 4. Comprehensive Multi-Page Flyer Deals (120+ Items across all 6 pages)
    # Format: (flyer_id, product_id, title, category, page_number, original_price, sale_price, unit_sale_price, discount_text, is_front)
    deals = [
        # --- NO FRILLS (6 Pages) ---
        # Page 1: Front Page Hot Deals
        (flyer_map["No Frills"], 2, "Boneless Skinless Chicken Thighs (Club Pack 1kg)", "Meat & Seafood", 1, 12.99, 9.99, "$0.99 / 100g", "Save $3.00 (23% OFF)", 1),
        (flyer_map["No Frills"], 12, "Cavendish Yellow Bananas (per kg)", "Produce", 1, 1.99, 1.39, "$0.14 / 100g", "Lowest Price in Edmonton", 1),
        (flyer_map["No Frills"], 5, "Neilson 2% Partly Skimmed Milk 4L Jug", "Dairy & Eggs", 1, 5.99, 5.19, "$0.13 / 100ml", "Rollback Deal", 1),
        (flyer_map["No Frills"], 6, "Large Grade A White Eggs (12-pack)", "Dairy & Eggs", 1, 4.19, 3.29, "$0.27 / item", "Haul of the Week", 1),
        (flyer_map["No Frills"], 23, "D'Italiano Thick Sliced Bread 675g", "Bakery & Deli", 1, 4.29, 2.49, "$0.37 / 100g", "Save $1.80", 1),

        # Page 2: Fresh Meat & Seafood
        (flyer_map["No Frills"], 3, "Lean Ground Beef (Family Value Pack 1kg)", "Meat & Seafood", 2, 12.99, 9.88, "$0.99 / 100g", "Save $3.11", 0),
        (flyer_map["No Frills"], 1, "Boneless Pork Loin Chops (1kg)", "Meat & Seafood", 2, 9.99, 6.99, "$0.70 / 100g", "Save $3.00", 0),
        (flyer_map["No Frills"], 4, "Fresh Atlantic Salmon Portions (400g)", "Meat & Seafood", 2, 12.99, 9.99, "$2.50 / 100g", "Save $3.00", 0),
        (flyer_map["No Frills"], 1, "Maple Leaf Naturally Smoked Bacon 375g", "Meat & Seafood", 2, 7.99, 4.99, "$1.33 / 100g", "Save $3.00 (38% OFF)", 0),
        (flyer_map["No Frills"], 1, "Schneiders Red Hot Wieners 375g", "Meat & Seafood", 2, 5.49, 3.99, "$1.06 / 100g", "Save $1.50", 0),

        # Page 3: Fresh Produce & Farm Market
        (flyer_map["No Frills"], 13, "Avocados (Bag of 5 Ripe Hass)", "Produce", 3, 5.49, 3.49, "$0.70 / item", "Save $2.00", 0),
        (flyer_map["No Frills"], 15, "Yellow Cooking Onions (3 lb bag)", "Produce", 3, 3.99, 2.49, "$0.18 / 100g", "Save $1.50", 0),
        (flyer_map["No Frills"], 12, "Russet Baking Potatoes (10 lb bag)", "Produce", 3, 6.99, 3.99, "$0.09 / 100g", "Save $3.00", 0),
        (flyer_map["No Frills"], 12, "Gala Apples (3 lb bag)", "Produce", 3, 5.99, 3.99, "$0.29 / 100g", "Save $2.00", 0),
        (flyer_map["No Frills"], 12, "Fresh California Strawberries (1 lb)", "Produce", 3, 4.99, 2.99, "$0.66 / 100g", "Save $2.00", 0),
        (flyer_map["No Frills"], 17, "Garlic Bulbs (Mesh Bag of 3)", "Produce", 3, 1.49, 0.88, "$0.29 / item", "Save $0.61", 0),

        # Page 4: Dairy, Cheese & Cold Case
        (flyer_map["No Frills"], 8, "No Name Salted Butter 454g Block", "Dairy & Eggs", 4, 5.99, 4.69, "$1.03 / 100g", "Save $1.30", 0),
        (flyer_map["No Frills"], 10, "Cracker Barrel Cheddar Cheese Block 400g", "Dairy & Eggs", 4, 6.99, 4.99, "$1.25 / 100g", "Save $2.00", 0),
        (flyer_map["No Frills"], 9, "Danone Activia Probiotic Yogurt 8x100g", "Dairy & Eggs", 4, 5.29, 3.49, "$0.44 / 100g", "Save $1.80", 0),
        (flyer_map["No Frills"], 11, "Dairyland 33% Whipping Cream 500ml", "Dairy & Eggs", 4, 4.29, 3.49, "$0.70 / 100ml", "Save $0.80", 0),
        (flyer_map["No Frills"], 10, "Philadelphia Original Cream Cheese 250g", "Dairy & Eggs", 4, 4.99, 3.49, "$1.40 / 100g", "Save $1.50", 0),

        # Page 5: Pantry & Canned Goods
        (flyer_map["No Frills"], 18, "Unico Crushed Tomatoes 796ml Can", "Pantry & Groceries", 5, 2.99, 1.88, "$0.24 / 100ml", "Save $1.11", 0),
        (flyer_map["No Frills"], 22, "Barilla Spaghetti Pasta 900g", "Pantry & Groceries", 5, 3.49, 2.19, "$0.24 / 100g", "Save $1.30", 0),
        (flyer_map["No Frills"], 21, "Heinz Tomato Ketchup 1L Squeeze", "Pantry & Groceries", 5, 5.99, 3.99, "$0.40 / 100ml", "Save $2.00", 0),
        (flyer_map["No Frills"], 20, "Tilda Pure Basmati Rice 4.54kg", "Pantry & Groceries", 5, 15.99, 11.99, "$0.26 / 100g", "Save $4.00", 0),
        (flyer_map["No Frills"], 19, "Suraj Indian Garam Masala 100g", "Pantry & Groceries", 5, 2.99, 1.99, "$1.99 / 100g", "Save $1.00", 0),
        (flyer_map["No Frills"], 18, "Campbell's Tomato Soup 284ml", "Pantry & Groceries", 5, 1.99, 0.99, "$0.35 / 100ml", "50% OFF", 0),

        # Page 6: Frozen, Bakery & Snacks
        (flyer_map["No Frills"], 22, "Delissio Thin Crispy Frozen Pizza 550g", "Frozen & Snacks", 6, 6.99, 4.49, "$0.82 / 100g", "Save $2.50", 0),
        (flyer_map["No Frills"], 12, "Cavendish Farms FlavourCrisp Fries 750g", "Frozen & Snacks", 6, 4.49, 2.79, "$0.37 / 100g", "Save $1.70", 0),
        (flyer_map["No Frills"], 23, "Chapman's Premium Ice Cream 2L Tub", "Frozen & Snacks", 6, 6.99, 4.49, "$0.22 / 100ml", "Save $2.50", 0),
        (flyer_map["No Frills"], 23, "Lay's Classic Potato Chips 235g", "Frozen & Snacks", 6, 4.29, 2.49, "$1.06 / 100g", "Save $1.80", 0),

        # --- WALMART (6 Pages) ---
        # Page 1: Rollback Front Page
        (flyer_map["Walmart"], 5, "Dairyland 2% Partly Skimmed Milk 4L", "Dairy & Eggs", 1, 6.19, 5.38, "$0.13 / 100ml", "Rollback Alert", 1),
        (flyer_map["Walmart"], 3, "Great Value Lean Ground Beef (1kg)", "Meat & Seafood", 1, 13.49, 10.97, "$1.10 / 100g", "Save $2.52", 1),
        (flyer_map["Walmart"], 14, "Del Monte Whole Golden Pineapple", "Produce", 1, 3.97, 2.47, "$2.47 / item", "Rollback Special", 1),
        (flyer_map["Walmart"], 10, "Black Diamond Cheddar Cheese Bar 400g", "Dairy & Eggs", 1, 6.77, 4.47, "$1.12 / 100g", "Save $2.30", 1),
        (flyer_map["Walmart"], 23, "Wonder White Sliced Bread 675g", "Bakery & Deli", 1, 3.49, 2.47, "$0.37 / 100g", "Save $1.02", 1),

        # Page 2: Meat, Poultry & Deli
        (flyer_map["Walmart"], 1, "Maple Leaf Prime Chicken Breasts (1kg)", "Meat & Seafood", 2, 14.97, 11.97, "$1.20 / 100g", "Save $3.00", 0),
        (flyer_map["Walmart"], 4, "Fresh Atlantic Salmon Fillet (500g)", "Meat & Seafood", 2, 14.97, 11.47, "$2.29 / 100g", "Save $3.50", 0),
        (flyer_map["Walmart"], 1, "Maple Leaf Smoked Bacon 375g", "Meat & Seafood", 2, 6.97, 4.47, "$1.19 / 100g", "Save $2.50", 0),
        (flyer_map["Walmart"], 1, "Marc Angelo Italian Sausage Pack (500g)", "Meat & Seafood", 2, 6.47, 4.97, "$0.99 / 100g", "Save $1.50", 0),
        (flyer_map["Walmart"], 1, "Pork Back Ribs (per kg)", "Meat & Seafood", 2, 10.97, 7.97, "$0.80 / 100g", "Save $3.00", 0),

        # Page 3: Fresh Produce
        (flyer_map["Walmart"], 16, "Organic Girl Baby Spinach 312g Tub", "Produce", 3, 5.97, 3.97, "$1.27 / 100g", "Save $2.00", 0),
        (flyer_map["Walmart"], 12, "Red Seedless Grapes (per kg)", "Produce", 3, 6.59, 3.97, "$0.40 / 100g", "Save $2.62", 0),
        (flyer_map["Walmart"], 12, "Sweet Bell Peppers (3-pack Rainbow)", "Produce", 3, 4.97, 3.47, "$1.16 / item", "Save $1.50", 0),
        (flyer_map["Walmart"], 12, "Crisp Iceberg Head Lettuce", "Produce", 3, 2.97, 1.67, "$1.67 / item", "Save $1.30", 0),
        (flyer_map["Walmart"], 12, "White Sliced Mushrooms 227g", "Produce", 3, 2.47, 1.67, "$0.74 / 100g", "Save $0.80", 0),
        (flyer_map["Walmart"], 12, "Honeycrisp Apples (per kg)", "Produce", 3, 6.59, 4.41, "$0.44 / 100g", "Save $2.18", 0),

        # Page 4: Dairy, Eggs & Beverages
        (flyer_map["Walmart"], 6, "Great Value Large Grade A Eggs (12-pk)", "Dairy & Eggs", 4, 3.98, 3.47, "$0.29 / item", "Rollback", 0),
        (flyer_map["Walmart"], 9, "Oikos 0% Plain Greek Yogurt 750g", "Dairy & Eggs", 4, 6.47, 4.97, "$0.66 / 100g", "Save $1.50", 0),
        (flyer_map["Walmart"], 8, "Gay Lea Salted Butter 454g", "Dairy & Eggs", 4, 5.97, 4.77, "$1.05 / 100g", "Save $1.20", 0),
        (flyer_map["Walmart"], 11, "Dairyland Whipping Cream 33% (500ml)", "Dairy & Eggs", 4, 4.19, 3.47, "$0.69 / 100ml", "Save $0.72", 0),
        (flyer_map["Walmart"], 5, "Silk Pure Almond Milk 1.89L", "Dairy & Eggs", 4, 4.47, 3.27, "$0.17 / 100ml", "Save $1.20", 0),

        # Page 5: Pantry & Groceries
        (flyer_map["Walmart"], 21, "Classico Pasta Sauce (Assorted 650ml)", "Pantry & Groceries", 5, 3.97, 2.47, "$0.38 / 100ml", "Save $1.50", 0),
        (flyer_map["Walmart"], 22, "Catelli Smart Spaghetti / Penne 500g", "Pantry & Groceries", 5, 2.77, 1.77, "$0.35 / 100g", "Save $1.00", 0),
        (flyer_map["Walmart"], 24, "Bertolli Extra Virgin Olive Oil 1L", "Pantry & Groceries", 5, 14.97, 10.97, "$1.10 / 100ml", "Save $4.00", 0),
        (flyer_map["Walmart"], 18, "Unico Chickpeas or Black Beans 540ml", "Pantry & Groceries", 5, 2.17, 1.47, "$0.27 / 100ml", "Save $0.70", 0),
        (flyer_map["Walmart"], 20, "Kraft Smooth Peanut Butter 1kg", "Pantry & Groceries", 5, 6.47, 4.97, "$0.50 / 100g", "Save $1.50", 0),
        (flyer_map["Walmart"], 20, "General Mills Cheerios Cereal 570g", "Pantry & Groceries", 5, 6.27, 3.97, "$0.70 / 100g", "Save $2.30", 0),

        # Page 6: Snacks, Drinks & Household
        (flyer_map["Walmart"], 23, "Lay's Family Size Potato Chips 235g", "Frozen & Snacks", 6, 3.97, 2.47, "$1.05 / 100g", "Save $1.50", 0),
        (flyer_map["Walmart"], 5, "Bubly Sparkling Water (12x355ml Cans)", "Frozen & Snacks", 6, 6.47, 4.47, "$0.11 / 100ml", "Save $2.00", 0),
        (flyer_map["Walmart"], 23, "Oreo Original Sandwich Cookies 303g", "Frozen & Snacks", 6, 3.97, 2.47, "$0.82 / 100g", "Save $1.50", 0),
        (flyer_map["Walmart"], 24, "Tide Liquid Laundry Detergent 2.04L", "Pantry & Groceries", 6, 13.97, 9.97, "$0.49 / 100ml", "Save $4.00", 0),

        # --- REAL CANADIAN SUPERSTORE (6 Pages) ---
        # Page 1: Optimum Member Doorcrashers
        (flyer_map["Superstore"], 1, "PC Boneless Skinless Chicken Breasts 1kg", "Meat & Seafood", 1, 15.49, 11.99, "$1.20 / 100g", "Optimum Member Price", 1),
        (flyer_map["Superstore"], 6, "Large Grade A White Eggs (12-pack)", "Dairy & Eggs", 1, 4.49, 3.49, "$0.29 / item", "Save $1.00", 1),
        (flyer_map["Superstore"], 8, "PC Salted or Unsalted Butter 454g", "Dairy & Eggs", 1, 6.49, 4.88, "$1.07 / 100g", "Save $1.61", 1),
        (flyer_map["Superstore"], 20, "Tilda Pure Original Basmati Rice 4.54kg", "Pantry & Groceries", 1, 16.99, 12.49, "$0.28 / 100g", "Save $4.50", 1),
        (flyer_map["Superstore"], 12, "PC Sweet Strawberries 1 lb Clamshell", "Produce", 1, 5.99, 3.49, "$0.77 / 100g", "Save $2.50", 1),

        # Page 2: Butcher & Seafood
        (flyer_map["Superstore"], 2, "PC Free From Chicken Thighs (1kg)", "Meat & Seafood", 2, 13.49, 10.49, "$1.05 / 100g", "Save $3.00", 0),
        (flyer_map["Superstore"], 3, "Lean Ground Beef (Club Pack 1kg)", "Meat & Seafood", 2, 13.49, 10.99, "$1.10 / 100g", "Save $2.50", 0),
        (flyer_map["Superstore"], 4, "Coho Salmon Fillets (Fresh 500g)", "Meat & Seafood", 2, 14.99, 11.99, "$2.40 / 100g", "Save $3.00", 0),
        (flyer_map["Superstore"], 1, "PC Thick Cut Smoked Bacon 500g", "Meat & Seafood", 2, 8.49, 5.99, "$1.20 / 100g", "Save $2.50", 0),
        (flyer_map["Superstore"], 1, "Whole Sterling Silver Beef Roast (1kg)", "Meat & Seafood", 2, 19.99, 14.99, "$1.50 / 100g", "Save $5.00", 0),

        # Page 3: Fresh Produce & Club Packs
        (flyer_map["Superstore"], 15, "Farmer's Market Yellow Onions (10 lb)", "Produce", 3, 8.99, 5.49, "$0.12 / 100g", "Club Pack Value", 0),
        (flyer_map["Superstore"], 12, "Honeycrisp Apples (5 lb Box)", "Produce", 3, 11.99, 7.99, "$0.35 / 100g", "Save $4.00", 0),
        (flyer_map["Superstore"], 13, "Hass Avocados (Bag of 6)", "Produce", 3, 6.49, 3.99, "$0.66 / item", "Save $2.50", 0),
        (flyer_map["Superstore"], 16, "PC Organics Baby Spinach 312g", "Produce", 3, 5.99, 3.99, "$1.28 / 100g", "Save $2.00", 0),
        (flyer_map["Superstore"], 12, "Hot House Beefsteak Tomatoes (per kg)", "Produce", 3, 4.39, 2.84, "$0.28 / 100g", "Save $1.55", 0),

        # Page 4: Dairy, Eggs & Cheese
        (flyer_map["Superstore"], 10, "Armstrong Cheddar Cheese Block 400g", "Dairy & Eggs", 4, 6.99, 4.79, "$1.20 / 100g", "Save $2.20", 0),
        (flyer_map["Superstore"], 5, "Dairyland 2% Milk 4L Jug", "Dairy & Eggs", 4, 5.79, 5.29, "$0.13 / 100ml", "Save $0.50", 0),
        (flyer_map["Superstore"], 9, "Iögo 0% Greek Yogurt 750g", "Dairy & Eggs", 4, 6.29, 4.49, "$0.60 / 100g", "Save $1.80", 0),
        (flyer_map["Superstore"], 10, "Black Diamond Cheese Strings 16-pack", "Dairy & Eggs", 4, 7.49, 4.99, "$0.31 / item", "Save $2.50", 0),
        (flyer_map["Superstore"], 11, "Neilson Whipping Cream 33% 500ml", "Dairy & Eggs", 4, 4.19, 3.49, "$0.70 / 100ml", "Save $0.70", 0),

        # Page 5: Groceries & International
        (flyer_map["Superstore"], 21, "Primo Pasta Sauce 680ml Can", "Pantry & Groceries", 5, 3.29, 1.99, "$0.29 / 100ml", "Save $1.30", 0),
        (flyer_map["Superstore"], 24, "PC Extra Virgin Olive Oil 1L", "Pantry & Groceries", 5, 14.99, 11.49, "$1.15 / 100ml", "Save $3.50", 0),
        (flyer_map["Superstore"], 19, "Suraj Authentic Indian Spices 100g", "Pantry & Groceries", 5, 2.99, 1.99, "$1.99 / 100g", "Save $1.00", 0),
        (flyer_map["Superstore"], 20, "Rooster Scented Jasmine Rice 8kg", "Pantry & Groceries", 5, 21.99, 16.99, "$0.21 / 100g", "Save $5.00", 0),
        (flyer_map["Superstore"], 18, "Unico Canned Chickpeas / Beans 540ml", "Pantry & Groceries", 5, 2.49, 1.49, "$0.28 / 100ml", "Save $1.00", 0),

        # Page 6: Bakery, Frozen & Snacks
        (flyer_map["Superstore"], 23, "PC The Decadent Cookies 300g", "Frozen & Snacks", 6, 4.49, 2.99, "$1.00 / 100g", "Save $1.50", 0),
        (flyer_map["Superstore"], 22, "Dr. Oetker Ristorante Pizza 350g", "Frozen & Snacks", 6, 5.99, 3.79, "$1.08 / 100g", "Save $2.20", 0),
        (flyer_map["Superstore"], 23, "D'Italiano Italian Bread 675g", "Bakery & Deli", 6, 4.29, 2.99, "$0.44 / 100g", "Save $1.30", 0),
        (flyer_map["Superstore"], 23, "PC Frozen Wild Blueberries 600g", "Frozen & Snacks", 6, 6.99, 4.99, "$0.83 / 100g", "Save $2.00", 0),
        (flyer_map["Superstore"], 20, "Starbucks Ground Coffee 340g", "Pantry & Groceries", 6, 11.99, 8.99, "$2.64 / 100g", "Save $3.00", 0),

        # --- SAFEWAY (5 Pages) ---
        (flyer_map["Safeway"], 4, "Fresh Atlantic Salmon Fillets (per kg)", "Meat & Seafood", 1, 24.90, 18.90, "$1.89 / 100g", "Scene+ Member Price", 1),
        (flyer_map["Safeway"], 3, "Sterling Silver Beef Oven Roast (per kg)", "Meat & Seafood", 1, 19.90, 13.90, "$1.39 / 100g", "Save $6.00", 1),
        (flyer_map["Safeway"], 5, "Lucerne 2% Milk 4L Jug", "Dairy & Eggs", 1, 6.49, 5.49, "$0.14 / 100ml", "Save $1.00", 1),
        (flyer_map["Safeway"], 6, "Compliments Large White Eggs (12-pk)", "Dairy & Eggs", 1, 4.69, 3.69, "$0.31 / item", "Save $1.00", 1),
        (flyer_map["Safeway"], 1, "Boneless Skinless Chicken Breasts 1kg", "Meat & Seafood", 2, 16.99, 12.99, "$1.30 / 100g", "Save $4.00", 0),
        (flyer_map["Safeway"], 1, "Compliments Smoked Bacon 500g", "Meat & Seafood", 2, 7.99, 5.49, "$1.10 / 100g", "Save $2.50", 0),
        (flyer_map["Safeway"], 12, "Gala or McIntosh Apples (per kg)", "Produce", 3, 5.49, 3.28, "$0.33 / 100g", "Save $2.21", 0),
        (flyer_map["Safeway"], 12, "Long English Seedless Cucumbers", "Produce", 3, 2.49, 1.29, "$1.29 / item", "Save $1.20", 0),
        (flyer_map["Safeway"], 10, "Black Diamond Cheddar Cheese Bar 400g", "Dairy & Eggs", 4, 7.49, 4.99, "$1.25 / 100g", "Save $2.50", 0),
        (flyer_map["Safeway"], 9, "Oikos Greek Yogurt 750g", "Dairy & Eggs", 4, 7.49, 5.49, "$0.73 / 100g", "Save $2.00", 0),
        (flyer_map["Safeway"], 21, "Classico Pasta Sauce 650ml", "Pantry & Groceries", 4, 4.49, 2.99, "$0.46 / 100ml", "Save $1.50", 0),
        (flyer_map["Safeway"], 24, "Bertolli Olive Oil 1L", "Pantry & Groceries", 4, 16.99, 12.99, "$1.30 / 100ml", "Save $4.00", 0),
        (flyer_map["Safeway"], 22, "Casa di Mama Frozen Pizza 410g", "Frozen & Snacks", 5, 6.49, 3.99, "$0.97 / 100g", "Save $2.50", 0),
        (flyer_map["Safeway"], 23, "Breyers Classic Ice Cream 1.66L", "Frozen & Snacks", 5, 6.99, 4.49, "$0.27 / 100ml", "Save $2.50", 0),

        # --- SAVE-ON-FOODS (5 Pages) ---
        (flyer_map["Save-On-Foods"], 2, "Western Family Chicken Thighs 1kg", "Meat & Seafood", 1, 13.99, 10.99, "$1.10 / 100g", "Darrell's Deal", 1),
        (flyer_map["Save-On-Foods"], 3, "Fresh Lean Ground Beef (1kg)", "Meat & Seafood", 1, 14.49, 11.49, "$1.15 / 100g", "Save $3.00", 1),
        (flyer_map["Save-On-Foods"], 5, "Western Family 2% Milk 4L Jug", "Dairy & Eggs", 1, 5.99, 5.39, "$0.13 / 100ml", "Save $0.60", 1),
        (flyer_map["Save-On-Foods"], 10, "Western Family Cheddar Cheese 400g", "Dairy & Eggs", 1, 7.49, 4.99, "$1.25 / 100g", "Save $2.50", 1),
        (flyer_map["Save-On-Foods"], 1, "Western Family Bacon 375g", "Meat & Seafood", 2, 7.49, 4.99, "$1.33 / 100g", "Save $2.50", 0),
        (flyer_map["Save-On-Foods"], 4, "Wild Sockeye Salmon Fillet (400g)", "Meat & Seafood", 2, 15.99, 11.99, "$3.00 / 100g", "Save $4.00", 0),
        (flyer_map["Save-On-Foods"], 12, "Organic Fair Trade Bananas (per kg)", "Produce", 3, 2.49, 1.79, "$0.18 / 100g", "Save $0.70", 0),
        (flyer_map["Save-On-Foods"], 12, "Honeycrisp BC Apples (3 lb bag)", "Produce", 3, 6.99, 4.99, "$0.37 / 100g", "BC Grown", 0),
        (flyer_map["Save-On-Foods"], 8, "Western Family Salted Butter 454g", "Dairy & Eggs", 4, 6.29, 4.99, "$1.10 / 100g", "Save $1.30", 0),
        (flyer_map["Save-On-Foods"], 21, "Western Family Organic Pasta Sauce", "Pantry & Groceries", 4, 4.29, 2.79, "$0.40 / 100ml", "Save $1.50", 0),
        (flyer_map["Save-On-Foods"], 20, "Western Family Basmati Rice 4.54kg", "Pantry & Groceries", 4, 15.99, 11.99, "$0.26 / 100g", "Save $4.00", 0),
        (flyer_map["Save-On-Foods"], 23, "Western Family Sourdough Bread 500g", "Bakery & Deli", 5, 4.49, 2.99, "$0.60 / 100g", "Bakery Fresh", 0),

        # --- COSTCO WHOLESALE (4 Pages) ---
        (flyer_map["Costco"], 1, "Kirkland Signature Chicken Breasts (Bulk 1kg)", "Meat & Seafood", 1, 13.49, 10.49, "$1.05 / 100g", "Instant $3 OFF", 1),
        (flyer_map["Costco"], 7, "Grade A White Eggs (Flat of 30 Eggs)", "Dairy & Eggs", 1, 9.49, 7.89, "$0.26 / item", "Instant Savings", 1),
        (flyer_map["Costco"], 24, "Kirkland Signature Olive Oil 2L Jug", "Pantry & Groceries", 1, 24.99, 18.99, "$0.95 / 100ml", "Instant $6 OFF", 1),
        (flyer_map["Costco"], 10, "Black Diamond Cheese Strings (40-pack)", "Dairy & Eggs", 1, 14.99, 10.99, "$0.27 / item", "Instant $4 OFF", 1),
        (flyer_map["Costco"], 3, "Kirkland Signature Ground Beef Extra Lean (2kg)", "Meat & Seafood", 2, 24.99, 19.99, "$1.00 / 100g", "Instant $5 OFF", 0),
        (flyer_map["Costco"], 4, "Fresh Steelhead Trout Fillets (per kg)", "Meat & Seafood", 2, 19.99, 15.99, "$1.60 / 100g", "Save $4.00", 0),
        (flyer_map["Costco"], 1, "Olympic Smoked Bacon (4x500g Multipack)", "Meat & Seafood", 2, 22.99, 16.99, "$0.85 / 100g", "Save $6.00", 0),
        (flyer_map["Costco"], 16, "Kirkland Signature Baby Spinach 454g Tub", "Produce", 3, 5.99, 3.99, "$0.88 / 100g", "Save $2.00", 0),
        (flyer_map["Costco"], 13, "Jumbo Hass Avocados (6-count Bag)", "Produce", 3, 8.99, 5.99, "$1.00 / item", "Save $3.00", 0),
        (flyer_map["Costco"], 20, "Tilda Pure Basmati Rice 10kg Sack", "Pantry & Groceries", 3, 27.99, 20.99, "$0.21 / 100g", "Save $7.00", 0),
        (flyer_map["Costco"], 21, "Rao's Homemade Marinara Sauce 2x790ml", "Pantry & Groceries", 3, 16.99, 11.99, "$0.76 / 100ml", "Instant $5 OFF", 0),
        (flyer_map["Costco"], 5, "Dairyland 2% Milk (2x4L Twin Pack)", "Dairy & Eggs", 4, 11.49, 10.29, "$0.13 / 100ml", "Warehouse Deal", 0),
        (flyer_map["Costco"], 9, "Chobani Greek Yogurt Variety (16x150g)", "Dairy & Eggs", 4, 14.99, 10.99, "$0.46 / 100g", "Instant $4 OFF", 0),
        (flyer_map["Costco"], 8, "Kirkland Signature Butter (4x454g Pack)", "Dairy & Eggs", 4, 21.99, 17.99, "$0.99 / 100g", "Save $4.00", 0),
    ]

    cursor.executemany("""
    INSERT INTO flyer_deals (flyer_id, product_id, title, category, page_number, original_price, sale_price, unit_sale_price, discount_text, is_front_page)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, deals)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    seed_edmonton_data(force=True)
    print("Database ready with 100+ comprehensive multi-page flyer deals.")
