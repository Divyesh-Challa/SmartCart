"""
SmartCart FastAPI Server
Provides REST API endpoints for recipe parsing, SKU lookup, postal code geocoding,
full multi-page weekly digital flyers, custom flyer uploads, and 3-mode basket optimization.
Serves the SmartCart Web Companion interface.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from pathlib import Path
import os
import base64
import re

from smartcart.database import init_db, seed_edmonton_data, get_connection, haversine_distance_km
from smartcart.parser import parse_recipe_text, parse_ingredient_line
from smartcart.normalizer import match_product_in_catalog, get_product_prices_across_stores
from smartcart.optimizer import BasketOptimizer, DEFAULT_USER_LAT, DEFAULT_USER_LON
from smartcart.geocoding import resolve_postal_code
from smartcart.gas_service import fetch_live_edmonton_gas_price, get_current_gas_price
from smartcart.flyers_service import (
    fetch_live_flyers,
    fetch_flyer_deals,
    search_flyer_items,
    get_city_for_postal_code,
    SUPPORTED_REGIONS
)

app = FastAPI(
    title="SmartCart API",
    description="AI-powered smart grocery intelligence, weekly digital flyers & multi-store basket optimizer",
    version="1.4.0"
)

@app.on_event("startup")
def startup_event():
    init_db()
    seed_edmonton_data()

class ParseRecipeRequest(BaseModel):
    recipe_text: Optional[str] = Field(None, description="Unstructured recipe or natural language grocery list text")
    text: Optional[str] = Field(None, description="Alternative field for recipe text")

class BasketItemRequest(BaseModel):
    name: str = Field(..., description="Item name or query")
    quantity: float = Field(1.0, description="Desired quantity")
    unit: str = Field("unit", description="Unit of measurement (kg, g, L, ml, unit, can, pack)")

class OptimizeBasketRequest(BaseModel):
    items: List[BasketItemRequest]
    postal_code: Optional[str] = Field(None, description="Canadian Postal Code (e.g. T5K 2X4, T6E 2A1, V6B 1A1)")
    user_lat: Optional[float] = Field(None, description="User latitude (overridden if postal_code provided)")
    user_lon: Optional[float] = Field(None, description="User longitude (overridden if postal_code provided)")
    max_radius_km: Optional[float] = Field(15.0, description="Max travel radius in km")
    radius_km: Optional[float] = Field(None, description="Alias for max_radius_km")
    exclude_membership: Optional[bool] = Field(False, description="Exclude stores requiring paid membership (e.g. Costco)")
    exclude_costco: Optional[bool] = Field(None, description="Alias for exclude_membership")
    gas_price_per_litre: Optional[float] = Field(None, description="Edmonton regular gas price in CAD/L (defaults to live price)")

class GeocodeRequest(BaseModel):
    query: str = Field(..., description="Postal code or neighborhood query")

class ComparisonRequest(BaseModel):
    items: List[BasketItemRequest]

class UploadFlyerRequest(BaseModel):
    banner: str = Field(..., description="Supermarket chain (e.g. No Frills, Walmart, Superstore)")
    page_number: int = Field(1, description="Page number 1 through 6")
    image_base64: str = Field(..., description="Base64 or Data URL of the flyer page image")
    title: Optional[str] = Field(None, description="Optional title for the flyer page")


class RecipeRequestModel(BaseModel):
    dish_name: str = Field(..., description="Recipe or ingredient requested")
    cuisine_preference: Optional[str] = Field(None, description="Cuisine or dietary goal")
    dietary_notes: Optional[str] = Field(None, description="Additional notes")
    user_email: Optional[str] = Field(None, description="User email")

class ReceiptCreateModel(BaseModel):
    store_name: str = Field(..., description="Grocery chain or store name")
    trip_date: str = Field(..., description="YYYY-MM-DD format date")
    amount_spent: float = Field(..., description="Actual paid amount in CAD")
    regular_amount: float = Field(..., description="Regular shelf price amount in CAD")
    category: Optional[str] = Field("Groceries", description="Primary shopping category")
    items_count: Optional[int] = Field(0, description="Number of items purchased")
    notes: Optional[str] = Field("", description="Trip notes or purchased items summary")

class AlertCreateModel(BaseModel):
    product_name: str = Field(..., description="Product to watch for flyer sales")
    category: Optional[str] = Field("Pantry", description="Department/category")
    target_price: Optional[float] = Field(None, description="Target notification price in CAD")

@app.get("/api/recipes/dinner-deals")
def get_dinner_deals(
    category: Optional[str] = Query(None, description="Filter by category: under_3_dollars, quick_weeknight, comfort, high_protein, one_pan"),
    banner: Optional[str] = Query(None, description="Filter by store banner: No Frills, Walmart, Superstore, Safeway"),
    search: Optional[str] = Query(None, description="Search in title or description")
):
    conn = get_connection()
    c = conn.cursor()
    query = """
    SELECT r.id, r.title, r.description, r.banner, r.cuisine, r.category,
           r.prep_time_minutes, r.servings, r.difficulty, r.cost_per_serving,
           r.total_sale_cost, r.total_regular_cost, r.savings_amount, r.savings_percent,
           r.badge_text, r.instructions_json
    FROM flyer_recipes r
    WHERE 1=1
    """
    params = []
    if category and category.lower() != 'all':
        query += " AND (LOWER(r.category) LIKE ? OR LOWER(r.category) = ?)"
        params.extend([f"%{category.lower()}%", category.lower()])
    if banner and banner.lower() != 'all':
        query += " AND LOWER(r.banner) = LOWER(?)"
        params.append(banner)
    if search:
        query += " AND (LOWER(r.title) LIKE ? OR LOWER(r.description) LIKE ?)"
        params.extend([f"%{search.lower()}%", f"%{search.lower()}%"])

    query += " ORDER BY r.cost_per_serving ASC, r.savings_amount DESC"
    c.execute(query, params)
    recipes = [dict(row) for row in c.fetchall()]

    for r in recipes:
        if r.get("instructions_json"):
            try:
                import json
                r["instructions"] = json.loads(r["instructions_json"])
            except Exception:
                r["instructions"] = []
        c.execute("""
            SELECT name, brand, package_size, category, sale_price, regular_price, savings, quantity, unit
            FROM flyer_recipe_ingredients
            WHERE recipe_id = ?
            ORDER BY id ASC
        """, (r["id"],))
        r["ingredients"] = [dict(ing) for ing in c.fetchall()]

    conn.close()
    return {"count": len(recipes), "recipes": recipes}

@app.get("/api/recipes/dinner-deals/{recipe_id}")
def get_single_dinner_deal(recipe_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM flyer_recipes WHERE id = ?", (recipe_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    recipe = dict(row)
    if recipe.get("instructions_json"):
        try:
            import json
            recipe["instructions"] = json.loads(recipe["instructions_json"])
        except Exception:
            recipe["instructions"] = []
    c.execute("""
        SELECT name, brand, package_size, category, sale_price, regular_price, savings, quantity, unit
        FROM flyer_recipe_ingredients
        WHERE recipe_id = ?
        ORDER BY id ASC
    """, (recipe_id,))
    recipe["ingredients"] = [dict(ing) for ing in c.fetchall()]
    conn.close()
    return recipe

@app.post("/api/recipes/request")
def submit_recipe_request(req: RecipeRequestModel):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO recipe_requests (dish_name, cuisine_preference, dietary_notes, user_email)
        VALUES (?, ?, ?, ?)
    """, (req.dish_name, req.cuisine_preference, req.dietary_notes, req.user_email))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": "Recipe request submitted successfully!"}

@app.get("/api/coverage/stats")
def get_coverage_stats():
    return {
        "total_stores_tracked": 3524,
        "display_stores": "3,500+",
        "alberta_stores": 267,
        "edmonton_metro_stores": 26,
        "banners_count": 35,
        "new_recipes_per_week": "500+",
        "provinces": [
            {"code": "ON", "name": "Ontario", "count": 1420},
            {"code": "QC", "name": "Quebec", "count": 680},
            {"code": "AB", "name": "Alberta", "count": 390},
            {"code": "BC", "name": "British Columbia", "count": 340},
            {"code": "NS", "name": "Nova Scotia", "count": 180},
            {"code": "NB", "name": "New Brunswick", "count": 120},
            {"code": "MB", "name": "Manitoba", "count": 115},
            {"code": "SK", "name": "Saskatchewan", "count": 95},
            {"code": "NL", "name": "Newfoundland", "count": 85},
            {"code": "PE", "name": "Prince Edward Island", "count": 40}
        ],
        "retailers": [
            {"name": "No Frills", "count": 348},
            {"name": "Walmart", "count": 420},
            {"name": "Real Canadian Superstore", "count": 160},
            {"name": "Metro", "count": 340},
            {"name": "Sobeys", "count": 310},
            {"name": "FreshCo", "count": 180},
            {"name": "Safeway", "count": 180},
            {"name": "Save-On-Foods", "count": 185},
            {"name": "Costco Wholesale", "count": 115},
            {"name": "Food Basics", "count": 145},
            {"name": "Maxi", "count": 170},
            {"name": "IGA", "count": 280}
        ]
    }

@app.get("/api/barcode/lookup")
def barcode_lookup(barcode: str = Query(..., description="UPC or EAN barcode number")):
    code_clean = barcode.strip()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM barcode_products WHERE barcode = ?", (code_clean,))
    row = c.fetchone()
    
    if row:
        p = dict(row)
        base = p["regular_price"] or p["sale_price"]
        other_chains = ["No Frills", "Walmart", "Superstore", "Metro", "Sobeys", "Safeway"]
        store_prices = [
            {"banner": p["banner"], "price": p["sale_price"], "is_sale": bool(p["is_on_sale"]), "is_lowest": True}
        ]
        for b in other_chains:
            if b != p["banner"]:
                mult = 1.08 if b in ["Metro", "Sobeys"] else (0.95 if b == "No Frills" else 1.0)
                sim_price = round(base * mult, 2)
                store_prices.append({
                    "banner": b,
                    "price": sim_price,
                    "is_sale": False,
                    "is_lowest": False
                })
        store_prices.sort(key=lambda x: x["price"])
        min_p = store_prices[0]["price"]
        for sp in store_prices:
            sp["is_lowest"] = (sp["price"] == min_p)

        conn.close()
        return {
            "found": True,
            "barcode": code_clean,
            "name": p["name"],
            "brand": p["brand"],
            "package_size": p["package_size"],
            "category": p["category"],
            "sale_price": p["sale_price"],
            "regular_price": p["regular_price"],
            "savings": round(p["regular_price"] - p["sale_price"], 2),
            "savings_percent": round((p["regular_price"] - p["sale_price"]) / p["regular_price"] * 100) if p["regular_price"] else 0,
            "banner": p["banner"],
            "is_on_sale": bool(p["is_on_sale"]),
            "image_url": p["image_url"],
            "nutrition": {
                "calories": p["calories"],
                "protein_g": p["protein_g"],
                "carbs_g": p["carbs_g"],
                "fat_g": p["fat_g"],
                "fiber_g": p["fiber_g"],
                "sodium_mg": p["sodium_mg"],
                "nutri_score": p["nutri_score"],
                "ingredients": p["ingredients_text"]
            },
            "store_prices": store_prices
        }
    
    # Real-Time Open Food Facts Canada API Lookup
    try:
        import urllib.request, json, ssl
        ssl_ctx = ssl._create_unverified_context()
        off_url = f"https://world.openfoodfacts.org/api/v0/product/{code_clean}.json"
        req = urllib.request.Request(
            off_url,
            headers={"User-Agent": "SmartCart-Canada - Version 2.0 - https://smartcart-9djq.onrender.com"}
        )
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=3.5) as resp:
            off_data = json.loads(resp.read().decode("utf-8"))
            if off_data.get("status") == 1 and off_data.get("product"):
                prod = off_data["product"]
                prod_name = prod.get("product_name") or prod.get("product_name_en") or "Scanned Canadian Grocery"
                brand = prod.get("brands") or "Canadian Grocer"
                pkg = prod.get("quantity") or "1 unit"
                img = prod.get("image_front_url") or "https://images.unsplash.com/photo-1542838132-92c53300491e?w=400&auto=format&fit=crop"
                nutri = (prod.get("nutriscore_grade") or "b").upper()
                nutriments = prod.get("nutriments", {})
                cals = int(nutriments.get("energy-kcal_100g") or nutriments.get("energy-kcal") or 150)
                prot = float(nutriments.get("proteins_100g") or nutriments.get("proteins") or 4.0)
                carbs = float(nutriments.get("carbohydrates_100g") or nutriments.get("carbohydrates") or 20.0)
                fat = float(nutriments.get("fat_100g") or nutriments.get("fat") or 3.0)
                fib = float(nutriments.get("fiber_100g") or nutriments.get("fiber") or 2.0)
                sod = round(float(nutriments.get("sodium_100g") or 0.1) * 1000, 1)
                ingred = prod.get("ingredients_text") or prod.get("ingredients_text_en") or "Ingredients listed on Canadian package."

                base_val = 3.99 + (hash(code_clean) % 30) * 0.1
                sale_p = round(base_val * 0.82, 2)
                reg_p = round(base_val * 1.18, 2)

                store_prices = [
                    {"banner": "No Frills", "price": sale_p, "is_sale": True, "is_lowest": True},
                    {"banner": "Walmart", "price": round(sale_p * 1.05, 2), "is_sale": False, "is_lowest": False},
                    {"banner": "Superstore", "price": round(sale_p * 1.02, 2), "is_sale": False, "is_lowest": False},
                    {"banner": "Metro", "price": round(reg_p * 1.04, 2), "is_sale": False, "is_lowest": False},
                    {"banner": "Sobeys", "price": round(reg_p * 1.06, 2), "is_sale": False, "is_lowest": False}
                ]
                store_prices.sort(key=lambda x: x["price"])

                try:
                    c.execute("""
                        INSERT OR REPLACE INTO barcode_products (
                            barcode, name, brand, package_size, category, sale_price, regular_price,
                            banner, is_on_sale, calories, protein_g, carbs_g, fat_g, fiber_g, sodium_mg,
                            nutri_score, ingredients_text, image_url
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        code_clean, prod_name, brand, pkg, "Grocery", sale_p, reg_p,
                        "No Frills", 1, cals, prot, carbs, fat, fib, sod, nutri, ingred, img
                    ))
                    conn.commit()
                except Exception:
                    pass

                conn.close()
                return {
                    "found": True,
                    "barcode": code_clean,
                    "name": prod_name,
                    "brand": brand,
                    "package_size": pkg,
                    "category": "Grocery",
                    "sale_price": sale_p,
                    "regular_price": reg_p,
                    "savings": round(reg_p - sale_p, 2),
                    "savings_percent": round((reg_p - sale_p) / reg_p * 100),
                    "banner": "No Frills",
                    "is_on_sale": True,
                    "image_url": img,
                    "nutrition": {
                        "calories": cals,
                        "protein_g": prot,
                        "carbs_g": carbs,
                        "fat_g": fat,
                        "fiber_g": fib,
                        "sodium_mg": sod,
                        "nutri_score": nutri,
                        "ingredients": ingred
                    },
                    "store_prices": store_prices
                }
    except Exception:
        pass

    # Catalog fallback
    c.execute("SELECT * FROM products WHERE name LIKE ? OR aliases LIKE ? LIMIT 1", (f"%{code_clean}%", f"%{code_clean}%"))
    prod_row = c.fetchone()
    conn.close()
    
    if prod_row:
        pr = dict(prod_row)
        return {
            "found": True,
            "barcode": code_clean,
            "name": pr["name"],
            "brand": pr["brand"] or "Canadian Grocer",
            "package_size": f"{pr['package_quantity']} {pr['package_unit']}",
            "category": pr["category"],
            "sale_price": 3.99,
            "regular_price": 5.49,
            "savings": 1.50,
            "savings_percent": 27,
            "banner": "No Frills",
            "is_on_sale": True,
            "image_url": "https://images.unsplash.com/photo-1542838132-92c53300491e?w=400&auto=format&fit=crop",
            "nutrition": {
                "calories": 140, "protein_g": 4.0, "carbs_g": 18.0, "fat_g": 2.0, "fiber_g": 2.0, "sodium_mg": 90.0,
                "nutri_score": "B", "ingredients": "Natural Canadian grocery ingredients."
            },
            "store_prices": [
                {"banner": "No Frills", "price": 3.99, "is_sale": True, "is_lowest": True},
                {"banner": "Walmart", "price": 4.47, "is_sale": False, "is_lowest": False},
                {"banner": "Superstore", "price": 4.29, "is_sale": False, "is_lowest": False}
            ]
        }

    return {
        "found": False,
        "barcode": code_clean,
        "message": f"Barcode {code_clean} not found in Canadian circular index. Try scanning one of the demo samples!"
    }

@app.get("/api/barcodes/samples")
def get_sample_barcodes():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT barcode, name, brand, package_size, sale_price, regular_price, banner, is_on_sale FROM barcode_products LIMIT 12")
    samples = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"samples": samples}

@app.get("/api/savings/summary")
def get_savings_summary():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT 
            COUNT(*) as trips_count,
            COALESCE(SUM(amount_spent), 0) as total_spent,
            COALESCE(SUM(regular_amount), 0) as total_regular,
            COALESCE(SUM(amount_saved), 0) as total_saved
        FROM receipts
    """)
    row = c.fetchone()
    trips_count = row["trips_count"]
    total_spent = round(row["total_spent"], 2)
    total_regular = round(row["total_regular"], 2)
    total_saved = round(row["total_saved"], 2)
    savings_percent = round((total_saved / total_regular * 100), 1) if total_regular > 0 else 0.0

    c.execute("""
        SELECT category, SUM(amount_saved) as saved, SUM(amount_spent) as spent
        FROM receipts
        GROUP BY category
        ORDER BY saved DESC
    """)
    categories = []
    for r in c.fetchall():
        cat_saved = round(r["saved"], 2)
        cat_spent = round(r["spent"], 2)
        categories.append({
            "category": r["category"],
            "saved": cat_saved,
            "spent": cat_spent,
            "share_percent": round(cat_saved / total_saved * 100, 1) if total_saved > 0 else 0
        })
    conn.close()
    return {
        "trips_count": trips_count,
        "total_spent": total_spent,
        "total_regular": total_regular,
        "total_saved": total_saved,
        "savings_percent": savings_percent,
        "avg_savings_per_trip": round(total_saved / trips_count, 2) if trips_count > 0 else 0.0,
        "categories": categories
    }

@app.get("/api/savings/receipts")
def get_savings_receipts():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM receipts ORDER BY trip_date DESC, id DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"receipts": rows}

@app.post("/api/savings/receipts")
def create_receipt(receipt: ReceiptCreateModel):
    spent = round(receipt.amount_spent, 2)
    regular = round(receipt.regular_amount, 2)
    saved = round(max(0.0, regular - spent), 2)
    pct = round((saved / regular * 100)) if regular > 0 else 0
    
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO receipts (store_name, trip_date, amount_spent, regular_amount, amount_saved, savings_percent, items_count, category, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (receipt.store_name, receipt.trip_date, spent, regular, saved, pct, receipt.items_count, receipt.category or "Groceries", receipt.notes or ""))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return {"status": "ok", "id": new_id, "amount_saved": saved, "savings_percent": pct}

@app.delete("/api/savings/receipts/{receipt_id}")
def delete_receipt(receipt_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "deleted": True}

@app.get("/api/alerts")
def get_alerts():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM sale_alerts ORDER BY is_on_sale DESC, id DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"alerts": rows}

@app.post("/api/alerts")
def create_alert(alert: AlertCreateModel):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT d.sale_price, d.original_price, f.banner
        FROM flyer_deals d
        JOIN flyers f ON f.id = d.flyer_id
        WHERE LOWER(d.title) LIKE ?
        ORDER BY d.sale_price ASC LIMIT 1
    """, (f"%{alert.product_name.lower().strip()}%",))
    deal_row = c.fetchone()
    
    is_on_sale = 1 if deal_row else 0
    curr_price = deal_row["sale_price"] if deal_row else None
    reg_price = deal_row["original_price"] if deal_row else None
    banner = deal_row["banner"] if deal_row else "Any Store"

    c.execute("""
        INSERT INTO sale_alerts (product_name, category, target_price, current_sale_price, regular_price, banner, is_on_sale)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (alert.product_name, alert.category or "Pantry", alert.target_price, curr_price, reg_price, banner, is_on_sale))
    conn.commit()
    alert_id = c.lastrowid
    conn.close()
    return {"status": "ok", "id": alert_id, "is_on_sale": bool(is_on_sale)}

@app.delete("/api/alerts/{alert_id}")
def delete_alert(alert_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM sale_alerts WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "deleted": True}

@app.get("/api/deals/top-ticker")
def get_top_deals_ticker():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT d.title, d.sale_price, d.original_price, d.discount_text, f.banner
        FROM flyer_deals d
        JOIN flyers f ON f.id = d.flyer_id
        WHERE d.original_price IS NOT NULL AND d.original_price > d.sale_price
        ORDER BY (d.original_price - d.sale_price) DESC
        LIMIT 14
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"deals": rows}

@app.post("/api/recipe/parse")
@app.post("/api/recipes/parse")
def parse_recipe(req: ParseRecipeRequest):
    input_text = req.recipe_text or req.text or ""
    parsed_items = parse_recipe_text(input_text)
    enriched = []
    for item in parsed_items:
        match = match_product_in_catalog(item["name"])
        enriched.append({
            "raw_text": item["raw_text"],
            "parsed_name": item["name"],
            "name": item["name"],
            "quantity": item["quantity"],
            "unit": item["unit"],
            "notes": item["notes"],
            "matched_product": match
        })
    return {"count": len(enriched), "items": enriched}

@app.get("/api/search")
def search_product(q: str = Query(..., description="Search term (e.g. banana, milk, chicken)")):
    q_clean = q.strip().lower()
    match = match_product_in_catalog(q_clean)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, category, brand, package_quantity, package_unit, standard_unit_type
        FROM products
        WHERE LOWER(name) LIKE ? OR LOWER(aliases) LIKE ?
    """, (f"%{q_clean}%", f"%{q_clean}%"))
    matching_rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Ensure match is included at top if found by normalizer
    matched_ids = {r["id"] for r in matching_rows}
    if match and match["id"] not in matched_ids:
        matching_rows.insert(0, match)

    results = []
    for r in matching_rows[:6]:
        prices = get_product_prices_across_stores(r["id"])
        min_price = min((p["price"] for p in prices), default=0.0)
        best_banner = next((p["banner"] for p in prices if p["price"] == min_price), "Edmonton Grocers")
        unit_p = next((p["unit_price"] for p in prices if p["price"] == min_price), 0.0)
        results.append({
            "id": r["id"],
            "name": r["name"],
            "category": r["category"],
            "brand": r["brand"],
            "package_size": f"{r['package_quantity']} {r['package_unit']}",
            "banner": best_banner,
            "price": min_price,
            "unit_price": unit_p,
            "std_type": r["standard_unit_type"]
        })

    prices = get_product_prices_across_stores(match["id"]) if match else []

    return {
        "query": q,
        "matched": bool(match or results),
        "product": match or (matching_rows[0] if matching_rows else None),
        "store_prices": prices,
        "results": results
    }

@app.post("/api/geocode")
def geocode_endpoint(req: GeocodeRequest):
    geo = resolve_postal_code(req.query)
    if not geo or not geo.get("supported"):
        return {
            "status": "error",
            "message": geo.get("message") if geo else f"Postal code '{req.query}' not recognized."
        }
    return {
        "status": "ok",
        "postal_code": geo.get("postal_code", req.query),
        "lat": geo.get("latitude", DEFAULT_USER_LAT),
        "lon": geo.get("longitude", DEFAULT_USER_LON),
        "neighborhood": geo.get("neighborhood", "Edmonton")
    }

@app.get("/api/location/postal-code")
def lookup_postal_code(code: str = Query(..., description="Canadian Postal Code (e.g. T5K 2X4, V6B 1A1)")):
    geo = resolve_postal_code(code)
    if not geo:
        raise HTTPException(
            status_code=404,
            detail=f"Postal code '{code}' not recognized as a valid Canadian postal code."
        )
    return geo

@app.get("/api/coverage/regions")
def get_coverage_regions():
    return {"regions": SUPPORTED_REGIONS}

@app.get("/api/stores/nearby")
@app.get("/api/stores")
def get_stores(
    postal_code: Optional[str] = Query(None, description="Optional postal code to calculate distance from"),
    city: Optional[str] = Query(None, description="Optional city filter (e.g. Edmonton, Calgary, Vancouver, Victoria)"),
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
    radius_km: Optional[float] = Query(None),
    quadrant: Optional[str] = Query(None, description="Filter by quadrant")
):
    resolved_location_name = "Edmonton Downtown (Default)"
    target_lat = DEFAULT_USER_LAT
    target_lon = DEFAULT_USER_LON

    if postal_code or city:
        query_loc = postal_code or city
        geo = resolve_postal_code(query_loc)
        if geo:
            target_lat = geo["latitude"]
            target_lon = geo["longitude"]
            resolved_location_name = f"{geo.get('city', '')} ({geo.get('postal_code', '')})"
    elif lat is not None and lon is not None:
        target_lat = lat
        target_lon = lon
        resolved_location_name = f"GPS ({round(lat, 4)}, {round(lon, 4)})"

    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT id, name, banner, address, city, postal_code, quadrant, latitude, longitude, requires_membership FROM stores"
    conditions = []
    params = []
    
    if quadrant:
        conditions.append("quadrant = ?")
        params.append(quadrant)
    if city and city.lower() != "all":
        conditions.append("LOWER(city) LIKE ?")
        params.append(f"%{city.lower()}%")
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    cursor.execute(query, params)
    stores = [dict(row) for row in cursor.fetchall()]
    conn.close()

    for s in stores:
        dist = haversine_distance_km(target_lat, target_lon, s["latitude"], s["longitude"])
        s["distance_km"] = dist
    stores.sort(key=lambda x: x["distance_km"])

    if radius_km:
        stores = [s for s in stores if s["distance_km"] <= radius_km]

    return {
        "supported": True,
        "user_location": {
            "name": resolved_location_name,
            "latitude": target_lat,
            "longitude": target_lon
        },
        "stores": stores
    }

@app.get("/api/flyers")
def get_flyers(
    postal_code: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    province: Optional[str] = Query(None)
):
    target_loc = postal_code or city or province or "T5K2X4"
    city_info = get_city_for_postal_code(target_loc)
    live_flyers = fetch_live_flyers(target_loc)
    gas_info = fetch_live_edmonton_gas_price(city_info.get("province_code", "AB"))
    return {
        "location": city_info,
        "city": city_info.get("city", "Edmonton"),
        "province": city_info.get("province", "Alberta"),
        "province_code": city_info.get("province_code", "AB"),
        "gas_price": gas_info.get("price_per_litre", 1.49),
        "flyers": live_flyers,
        "count": len(live_flyers)
    }

@app.get("/api/flyers/deals")
@app.get("/api/flyers/catalog/deals")
def get_catalog_flyer_deals(
    banner: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    page_number: Optional[int] = Query(None),
    front_page_only: Optional[bool] = Query(False),
    search: Optional[str] = Query(None)
):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT d.id, d.flyer_id, d.product_id, d.title as name, d.category, d.page_number, d.original_price,
           d.sale_price, d.unit_sale_price as std_price, d.discount_text, d.is_front_page,
           f.banner, f.valid_from, f.valid_to,
           p.name as matched_product_name, p.package_quantity, p.package_unit,
           p.standard_unit_type as std_type,
           printf('%g %s', p.package_quantity, p.package_unit) as package_size,
           COALESCE(d.original_price, d.sale_price) as price
    FROM flyer_deals d
    JOIN flyers f ON f.id = d.flyer_id
    LEFT JOIN products p ON p.id = d.product_id
    WHERE 1=1
    """
    params = []
    if banner and banner.lower() != 'all':
        query += " AND LOWER(f.banner) = LOWER(?)"
        params.append(banner)
    if category and category.lower() != 'all':
        query += " AND LOWER(d.category) = LOWER(?)"
        params.append(category)
    if page_number:
        query += " AND d.page_number = ?"
        params.append(page_number)
    if front_page_only:
        query += " AND d.is_front_page = 1"
    if search:
        query += " AND (d.title LIKE ? OR d.category LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")

    query += " ORDER BY d.is_front_page DESC, d.page_number ASC, d.sale_price ASC"
    cursor.execute(query, params)
    deals = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"count": len(deals), "deals": deals}

@app.get("/api/flyers/search")
def search_deals(
    q: str = Query(..., description="Item search query (e.g. butter, eggs, milk)"),
    postal_code: Optional[str] = Query(None),
    city: Optional[str] = Query(None)
):
    loc = postal_code or city or "T5K2X4"
    results = search_flyer_items(q, loc)
    return {
        "query": q,
        "location": loc,
        "results": results,
        "count": len(results)
    }

@app.get("/api/flyers/{flyer_id}/items")
@app.get("/api/flyers/{flyer_id}/deals")
def get_flyer_items(flyer_id: int):
    deals = fetch_flyer_deals(flyer_id)
    return {
        "flyer_id": flyer_id,
        "deals": deals,
        "count": len(deals)
    }

@app.get("/api/flyers/custom-pages")
def get_custom_flyer_pages():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT banner, page_number, image_url, title, created_at FROM custom_flyer_pages ORDER BY banner, page_number")
    pages = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"custom_pages": pages}

@app.post("/api/flyers/upload")
def upload_custom_flyer_page(req: UploadFlyerRequest):
    banner_clean = re.sub(r'[^a-zA-Z0-9]', '_', req.banner).lower()
    filename = f"{banner_clean}_p{req.page_number}.png"
    upload_dir = Path(__file__).parent / "static" / "uploads" / "flyers"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target_path = upload_dir / filename

    raw_b64 = req.image_base64
    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]

    try:
        img_bytes = base64.b64decode(raw_b64)
        target_path.write_bytes(img_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to decode image: {str(e)}")

    image_url = f"/static/uploads/flyers/{filename}"

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO custom_flyer_pages (banner, page_number, image_url, title)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(banner, page_number) DO UPDATE SET
            image_url = excluded.image_url,
            title = excluded.title,
            created_at = CURRENT_TIMESTAMP
    """, (req.banner, req.page_number, image_url, req.title or f"{req.banner} Page {req.page_number}"))
    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "banner": req.banner,
        "page_number": req.page_number,
        "image_url": image_url
    }

@app.delete("/api/flyers/custom-page")
def delete_custom_flyer_page(banner: str = Query(...), page_number: int = Query(...)):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM custom_flyer_pages WHERE LOWER(banner) = LOWER(?) AND page_number = ?", (banner, page_number))
    conn.commit()
    conn.close()
    return {"status": "ok", "deleted": True}

@app.get("/api/gas-price")
def get_gas_price_endpoint():
    """Returns the latest real-time regular fuel price for Edmonton, AB."""
    return fetch_live_edmonton_gas_price()

@app.post("/api/basket/optimize")
@app.post("/api/optimize")
def optimize_basket(req: OptimizeBasketRequest):
    if not req.items:
        raise HTTPException(status_code=400, detail="Shopping list cannot be empty.")

    target_lat = req.user_lat if req.user_lat is not None else DEFAULT_USER_LAT
    target_lon = req.user_lon if req.user_lon is not None else DEFAULT_USER_LON
    location_label = "Edmonton Downtown"
    user_postal_code = "T5J 1N2"

    if req.postal_code:
        geo = resolve_postal_code(req.postal_code)
        if geo:
            if not geo.get("supported"):
                raise HTTPException(status_code=400, detail=geo.get("message"))
            target_lat = geo["latitude"] or target_lat
            target_lon = geo["longitude"] or target_lon
            location_label = f"{geo['postal_code']} ({geo['neighborhood']})"
            user_postal_code = geo["postal_code"]

    radius = req.radius_km if req.radius_km is not None else (req.max_radius_km or 15.0)
    exclude_m = req.exclude_costco if req.exclude_costco is not None else (req.exclude_membership or False)
    gas_price = req.gas_price_per_litre if req.gas_price_per_litre is not None else get_current_gas_price()

    optimizer = BasketOptimizer(
        user_lat=target_lat,
        user_lon=target_lon,
        max_travel_radius_km=radius,
        exclude_membership_stores=exclude_m,
        gas_price_per_litre=gas_price
    )

    items_dict = [it.dict() for it in req.items]
    result = optimizer.optimize_basket(items_dict)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    origin_query = f"{user_postal_code}, Edmonton, AB"

    # Normalize plan structures to support all frontend conventions
    for plan_key, plan in result.get("plans", {}).items():
        if not plan:
            continue
        plan["total_cost"] = plan.get("all_in_cost", 0.0)
        plan["grocery_total"] = plan.get("grocery_cost", 0.0)
        plan["gas_cost"] = plan.get("gas_cost", plan.get("estimated_travel_cost", 0.0))
        plan["travel_cost"] = plan["gas_cost"]
        plan["savings_vs_single"] = plan.get("savings_vs_market_avg", 0.0)
        plan["savings_percent"] = plan.get("pct_savings", 0.0)
        plan["total_distance_km"] = plan.get("total_distance_km", round(plan.get("distance_km", 0.0) * 2, 2))
        plan["drive_time_minutes"] = plan.get("drive_time_minutes", max(4, round(plan["total_distance_km"] * 2.0)))
        plan["gas_price_per_litre"] = optimizer.gas_price_per_litre
        plan["fuel_efficiency_l_100km"] = optimizer.fuel_efficiency_l_100km

        if "store_groups" in plan and plan["store_groups"]:
            standard_stores = []
            for g in plan["store_groups"]:
                s_meta = g["store"]
                dest_query = f"{s_meta['name']}, {s_meta['address']}, Edmonton, AB"
                standard_stores.append({
                    "store_name": s_meta["name"],
                    "chain": s_meta["banner"],
                    "address": s_meta["address"],
                    "store_subtotal": g["subtotal"],
                    "items": g["items"],
                    "leg_km": g.get("leg_km", s_meta.get("distance_km", 0.0)),
                    "distance_from_user_km": g.get("distance_from_user_km", s_meta.get("distance_km", 0.0)),
                    "directions_url": f"https://www.google.com/maps/dir/?api=1&origin={origin_query}&destination={dest_query}&travelmode=driving"
                })
            plan["stores"] = standard_stores

            store_addrs = [f"{st['store_name']}, {st['address']}, Edmonton, AB" for st in standard_stores]
            if len(store_addrs) > 1:
                plan["full_route_directions_url"] = f"https://www.google.com/maps/dir/?api=1&origin={origin_query}&destination={origin_query}&waypoints={'|'.join(store_addrs)}&travelmode=driving"
            elif len(store_addrs) == 1:
                plan["full_route_directions_url"] = f"https://www.google.com/maps/dir/?api=1&origin={origin_query}&destination={store_addrs[0]}&travelmode=driving"
            else:
                plan["full_route_directions_url"] = ""

        elif "store" in plan and plan["store"]:
            s_meta = plan["store"]
            dest_query = f"{s_meta['name']}, {s_meta['address']}, Edmonton, AB"
            one_store = {
                "store_name": s_meta["name"],
                "chain": s_meta["banner"],
                "address": s_meta["address"],
                "store_subtotal": plan.get("grocery_cost", 0.0),
                "items": plan.get("items", []),
                "leg_km": s_meta.get("distance_km", 0.0),
                "distance_from_user_km": s_meta.get("distance_km", 0.0),
                "directions_url": f"https://www.google.com/maps/dir/?api=1&origin={origin_query}&destination={dest_query}&travelmode=driving"
            }
            plan["stores"] = [one_store]
            plan["full_route_directions_url"] = one_store["directions_url"]
        else:
            plan["stores"] = []
            plan["full_route_directions_url"] = ""

    result["user_location"]["label"] = location_label
    result["user_location"]["postal_code"] = user_postal_code
    return result

@app.post("/api/comparison")
def compare_prices(req: ComparisonRequest):
    if not req.items:
        return {"matrix": []}

    chains = ["Superstore", "Walmart", "No Frills", "Safeway", "Costco", "Save-On-Foods"]
    matrix = []

    for it in req.items:
        match = match_product_in_catalog(it.name)
        if not match:
            continue

        prices = get_product_prices_across_stores(match["id"])
        chain_prices = {}
        for p in prices:
            b = p["banner"]
            if b not in chain_prices or p["price"] < chain_prices[b]["price"]:
                chain_prices[b] = p

        lowest_price = min((cp["price"] for cp in chain_prices.values()), default=float("inf"))
        row_prices = []
        for ch in chains:
            p_info = chain_prices.get(ch)
            if p_info:
                row_prices.append({
                    "chain": ch,
                    "price": p_info["price"],
                    "std_price": p_info["unit_price"],
                    "is_lowest": (p_info["price"] == lowest_price)
                })

        matrix.append({
            "item_name": match["name"],
            "prices": row_prices
        })

    return {"matrix": matrix}

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return "<h1>SmartCart API is running. Web companion UI not found.</h1>"
