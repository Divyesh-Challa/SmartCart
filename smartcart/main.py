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

@app.get("/api/stores/nearby")
@app.get("/api/stores")
def get_stores(
    postal_code: Optional[str] = Query(None, description="Optional postal code to calculate distance from"),
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
    radius_km: Optional[float] = Query(None),
    quadrant: Optional[str] = Query(None, description="Filter by quadrant (Central, South, West, East, North, Region)")
):
    resolved_location_name = "Edmonton Downtown (Default)"
    target_lat = DEFAULT_USER_LAT
    target_lon = DEFAULT_USER_LON

    if postal_code:
        geo = resolve_postal_code(postal_code)
        if geo:
            if not geo.get("supported"):
                return {
                    "supported": False,
                    "message": geo.get("message"),
                    "stores": []
                }
            target_lat = geo["latitude"]
            target_lon = geo["longitude"]
            resolved_location_name = f"{geo['postal_code']} - {geo['neighborhood']}"
    elif lat is not None and lon is not None:
        target_lat = lat
        target_lon = lon
        resolved_location_name = f"GPS ({round(lat, 4)}, {round(lon, 4)})"

    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT id, name, banner, address, postal_code, quadrant, latitude, longitude, requires_membership FROM stores"
    params = []
    if quadrant:
        query += " WHERE quadrant = ?"
        params.append(quadrant)
        
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
def get_flyers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT f.id, f.banner, f.title, f.total_pages, f.valid_from, f.valid_to, f.badge_text, f.color_theme,
           COUNT(d.id) as deal_count
    FROM flyers f
    LEFT JOIN flyer_deals d ON d.flyer_id = f.id
    GROUP BY f.id
    ORDER BY f.id ASC
    """)
    flyers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"flyers": flyers}

@app.get("/api/flyers/deals")
def get_flyer_deals(
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
