"""
SmartCart Unit Normalizer and Semantic SKU Matcher
Normalizes measurements to standard comparison baselines ($/100g, $/100ml, $/unit)
and matches natural language ingredient queries to catalog SKUs.
"""

import math
import re
from typing import Dict, Any, List, Optional, Tuple
from smartcart.database import get_connection

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

def tokenize(text: str) -> set:
    words = re.findall(r"\b\w+\b", text.lower())
    stop_words = {"fresh", "organic", "large", "small", "can", "bag", "pack", "white", "for", "with", "and"}
    return {w for w in words if w not in stop_words}

def match_product_in_catalog(query: str, preferred_category: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, name, category, brand, package_quantity, package_unit,
           standard_unit_type, normalized_amount, aliases
    FROM products
    """)
    products = [dict(row) for row in cursor.fetchall()]
    conn.close()

    query_tokens = tokenize(query)
    if not query_tokens:
        return None

    best_match = None
    best_score = -1.0

    for prod in products:
        score = 0.0
        prod_tokens = tokenize(prod["name"])
        alias_tokens = tokenize(prod["aliases"] or "")

        aliases = [a.strip().lower() for a in (prod["aliases"] or "").split(",") if a.strip()]
        if query.strip().lower() in aliases:
            score += 10.0

        if query.lower() in prod["name"].lower():
            score += 8.0

        overlap_name = len(query_tokens.intersection(prod_tokens))
        overlap_alias = len(query_tokens.intersection(alias_tokens))
        score += (overlap_name * 3.0) + (overlap_alias * 2.0)

        all_candidate_tokens = prod_tokens.union(alias_tokens)
        if not query_tokens.intersection(all_candidate_tokens):
            continue

        if preferred_category and prod["category"].lower() == preferred_category.lower():
            score += 2.0

        if score > best_score:
            best_score = score
            best_match = prod

    if best_score > 0 and best_match:
        return best_match
    return None

def compute_packages_needed(required_qty: float, required_unit: str, product: Dict[str, Any]) -> int:
    std_type, req_norm = normalize_quantity_to_standard(required_qty, required_unit)

    prod_std_type = product["standard_unit_type"]
    prod_norm_per_pack = product["normalized_amount"]

    if std_type == prod_std_type and prod_norm_per_pack > 0:
        packs = math.ceil(req_norm / prod_norm_per_pack)
        return max(1, packs)

    return max(1, math.ceil(required_qty))

def get_product_prices_across_stores(product_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT s.id as store_id, s.name as store_name, s.banner, s.address, s.latitude, s.longitude,
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
    return rows
