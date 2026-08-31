"""
SmartCart Unit Normalizer and Semantic SKU Matcher
Normalizes measurements to standard comparison baselines ($/100g, $/100ml, $/unit)
and matches natural language ingredient queries to catalog SKUs.
"""

import math
import re
from typing import Dict, Any, List, Optional, Tuple
from smartcart.database import get_connection, haversine_distance_km

def normalize_barcode(raw_code: str) -> str:
    """
    Cleans raw scanned barcode input, removes non-alphanumeric chars (spaces, hyphens),
    and strips leading zero if 13-digit EAN-13 begins with '0' (UPC-A padded format).
    """
    if not raw_code:
        return ""
    clean = re.sub(r'[^a-zA-Z0-9]', '', str(raw_code).strip())
    if len(clean) == 13 and clean.startswith('0') and clean.isdigit():
        return clean[1:]
    return clean


WEIGHT_TO_GRAMS = {
    "g": 1.0,
    "kg": 1000.0,
    "lb": 453.592,
    "oz": 28.3495,
}

VOLUME_TO_ML = {
    "ml": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "litre": 1000.0,
    "liters": 1000.0,
    "litres": 1000.0,
    "cup": 236.588,
    "tbsp": 14.7868,
    "tsp": 4.92892,
    "fl oz": 29.5735,
}

UNIT_MULTIPLIERS = {
    "unit": 1.0,
    "piece": 1.0,
    "dozen": 12.0,
    "can": 1.0,
    "pack": 1.0,
    "bag": 1.0,
    "block": 1.0,
    "clove": 0.33,
    "head": 1.0,
}

def normalize_quantity_to_standard(quantity: float, unit: str) -> Tuple[str, float]:
    unit_lower = unit.lower().strip()

    if unit_lower in WEIGHT_TO_GRAMS:
        total_grams = quantity * WEIGHT_TO_GRAMS[unit_lower]
        return "weight_100g", total_grams / 100.0

    if unit_lower in VOLUME_TO_ML:
        total_ml = quantity * VOLUME_TO_ML[unit_lower]
        return "volume_100ml", total_ml / 100.0

    multiplier = UNIT_MULTIPLIERS.get(unit_lower, 1.0)
    return "unit", quantity * multiplier

import time

_PRODUCT_CATALOG_CACHE: Optional[List[Dict[str, Any]]] = None
_CACHE_TIMESTAMP: float = 0.0
_CACHE_TTL_SECONDS: float = 120.0

def get_cached_products() -> List[Dict[str, Any]]:
    global _PRODUCT_CATALOG_CACHE, _CACHE_TIMESTAMP
    now = time.time()
    if _PRODUCT_CATALOG_CACHE is None or (now - _CACHE_TIMESTAMP) > _CACHE_TTL_SECONDS:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, name, category, brand, package_quantity, package_unit,
               standard_unit_type, normalized_amount, aliases
        FROM products
        """)
        _PRODUCT_CATALOG_CACHE = [dict(row) for row in cursor.fetchall()]
        _CACHE_TIMESTAMP = now
        conn.close()
    return _PRODUCT_CATALOG_CACHE

def tokenize(text: str) -> set:
    words = re.findall(r"\b\w+\b", text.lower())
    stop_words = {"fresh", "organic", "large", "small", "can", "canned", "bag", "pack", "white", "for", "with", "and", "the", "of", "a", "an"}
    return {w for w in words if w not in stop_words}

# Modifier conflict dictionary: if query contains key, candidate possessing conflicting values is heavily penalized
CONFLICTING_MODIFIERS = {
    "butter": {"peanut", "almond", "apple", "cookie"},
    "cream": {"ice", "shaving", "sour", "tartar"},
    "chicken": {"broth", "bouillon", "noodle", "soup"},
    "beef": {"broth", "bouillon", "jerky"},
    "onions": {"crispy", "rings"},
    "cheese": {"cream", "cottage"}
}

def match_product_in_catalog(query: str, preferred_category: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not query:
        return None

    products = get_cached_products()
    query_clean = query.strip().lower()
    query_tokens = tokenize(query_clean)
    if not query_tokens:
        return None

    best_match = None
    best_score = -1.0

    for prod in products:
        score = 0.0
        prod_name_lower = prod["name"].lower()
        prod_tokens = tokenize(prod_name_lower)
        alias_tokens = tokenize(prod["aliases"] or "")
        all_candidate_tokens = prod_tokens.union(alias_tokens)

        # 1. Exact alias match
        aliases = [a.strip().lower() for a in (prod["aliases"] or "").split(",") if a.strip()]
        if query_clean in aliases:
            score += 25.0

        # 2. Exact product name match or substring
        if query_clean == prod_name_lower:
            score += 20.0
        elif query_clean in prod_name_lower:
            score += 12.0
        elif prod_name_lower in query_clean:
            score += 10.0

        # 3. Token Overlap
        overlap_name = len(query_tokens.intersection(prod_tokens))
        overlap_alias = len(query_tokens.intersection(alias_tokens))
        overlap_total = len(query_tokens.intersection(all_candidate_tokens))

        if overlap_total == 0 and score == 0.0:
            continue

        score += (overlap_name * 4.0) + (overlap_alias * 2.5)

        # 4. Conflicting Modifiers Penalty (prevents matching peanut butter to butter, or ice cream to cream)
        for base_food, conflicting_set in CONFLICTING_MODIFIERS.items():
            if base_food in query_tokens:
                # If query does NOT have the modifier, but candidate DOES: penalize heavily
                for conf in conflicting_set:
                    if conf not in query_tokens and (conf in prod_tokens or conf in alias_tokens):
                        score -= 15.0
                    # If query HAS the modifier, but candidate lacks it: penalize
                    elif conf in query_tokens and conf not in prod_tokens and conf not in alias_tokens:
                        score -= 15.0

        # 5. Category congruence
        if preferred_category and prod["category"].lower() == preferred_category.lower():
            score += 4.0

        # 6. Precision ratio check (query tokens matched / total query tokens)
        precision_ratio = overlap_total / max(1, len(query_tokens))
        score += precision_ratio * 3.0

        if score > best_score and score >= 4.0:
            best_score = score
            best_match = prod

    return best_match

def compute_packages_needed(required_qty: float, required_unit: str, product: Dict[str, Any]) -> int:
    std_type, req_norm = normalize_quantity_to_standard(required_qty, required_unit)

    prod_std_type = product["standard_unit_type"]
    prod_norm_per_pack = product["normalized_amount"]

    if std_type == prod_std_type and prod_norm_per_pack > 0:
        packs = math.ceil(req_norm / prod_norm_per_pack)
        return max(1, packs)

    return max(1, math.ceil(required_qty))

def get_product_prices_across_stores(
    product_id: int,
    user_lat: Optional[float] = None,
    user_lon: Optional[float] = None,
    max_radius_km: float = 25.0,
    city: Optional[str] = None
) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT s.id as store_id, s.name as store_name, s.banner, s.address, s.city, s.latitude, s.longitude,
           s.requires_membership,
           i.price, i.unit_price, i.in_stock, i.confidence_score,
           p.name as product_name, p.standard_unit_type, p.package_quantity, p.package_unit
    FROM store_inventory i
    JOIN stores s ON s.id = i.store_id
    JOIN products p ON p.id = i.product_id
    WHERE i.product_id = ?
    ORDER BY i.unit_price ASC
    """, (product_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if user_lat is not None and user_lon is not None:
        filtered = []
        for r in rows:
            dist = haversine_distance_km(user_lat, user_lon, r["latitude"], r["longitude"])
            if dist <= max_radius_km:
                r["distance_km"] = round(dist, 1)
                filtered.append(r)
        if not filtered and rows:
            # Rural or wide radius fallback: find nearest stores within 50 km
            for r in rows:
                dist = haversine_distance_km(user_lat, user_lon, r["latitude"], r["longitude"])
                r["distance_km"] = round(dist, 1)
            rows.sort(key=lambda x: (x.get("distance_km", 999), x["unit_price"]))
            return rows[:15]
        filtered.sort(key=lambda x: (x["unit_price"], x.get("distance_km", 999)))
        return filtered
    elif city:
        city_lower = city.strip().lower()
        city_rows = [r for r in rows if r.get("city", "").lower() == city_lower or city_lower in r.get("store_name", "").lower()]
        if city_rows:
            return city_rows

    return rows[:25]
