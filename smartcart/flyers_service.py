"""
SmartCart Canadian Grocery Flyer & Deals Service

Flyers and their deals are read from the local database only. They are entered
by an admin or will arrive through a licensed flyer data feed; nothing here
calls third-party flyer APIs, and nothing is invented when no flyer is on file.
"""

import re
from typing import List, Dict, Any

from smartcart.config import local_today
from smartcart.database import get_connection

# Supported Canadian Regions & Cities with their primary postal codes
SUPPORTED_REGIONS = {
    "Alberta": {
        "province_code": "AB",
        "description": "Edmonton, Calgary, Red Deer, Lethbridge & across Alberta",
        "cities": [
            {"city": "Edmonton", "postal_code": "T5K 2X4", "fsa": "T5K", "lat": 53.5444, "lon": -113.4909, "stores_count": 142},
            {"city": "Calgary", "postal_code": "T2P 1J9", "fsa": "T2P", "lat": 51.0486, "lon": -114.0708, "stores_count": 168},
            {"city": "Red Deer", "postal_code": "T4N 1X5", "fsa": "T4N", "lat": 52.2681, "lon": -113.8112, "stores_count": 48},
            {"city": "Lethbridge", "postal_code": "T1J 0P4", "fsa": "T1J", "lat": 49.6956, "lon": -112.8451, "stores_count": 39},
            {"city": "Medicine Hat", "postal_code": "T1A 0A1", "fsa": "T1A", "lat": 50.0417, "lon": -110.6775, "stores_count": 26},
            {"city": "St. Albert", "postal_code": "T8N 4K6", "fsa": "T8N", "lat": 53.6331, "lon": -113.6268, "stores_count": 22},
            {"city": "Sherwood Park", "postal_code": "T8A 0A1", "fsa": "T8A", "lat": 53.5358, "lon": -113.3182, "stores_count": 24},
            {"city": "Fort McMurray", "postal_code": "T9H 1K1", "fsa": "T9H", "lat": 56.7264, "lon": -111.3803, "stores_count": 19},
        ],
        "key_banners": ["No Frills", "Superstore", "Walmart", "Calgary Co-op", "Safeway", "Sobeys", "Save-On-Foods", "FreshCo", "T&T Supermarket", "Costco"]
    },
    "British Columbia": {
        "province_code": "BC",
        "description": "Vancouver, Victoria, Kelowna, Surrey & across British Columbia",
        "cities": [
            {"city": "Vancouver", "postal_code": "V6B 1A1", "fsa": "V6B", "lat": 49.2827, "lon": -123.1207, "stores_count": 194},
            {"city": "Victoria", "postal_code": "V8W 1P6", "fsa": "V8W", "lat": 48.4284, "lon": -123.3656, "stores_count": 64},
            {"city": "Surrey", "postal_code": "V3T 1V7", "fsa": "V3T", "lat": 49.1913, "lon": -122.8490, "stores_count": 112},
            {"city": "Burnaby", "postal_code": "V5H 4C2", "fsa": "V5H", "lat": 49.2488, "lon": -122.9805, "stores_count": 78},
            {"city": "Richmond", "postal_code": "V6X 1X1", "fsa": "V6X", "lat": 49.1666, "lon": -123.1336, "stores_count": 72},
            {"city": "Kelowna", "postal_code": "V1Y 1Z9", "fsa": "V1Y", "lat": 49.8880, "lon": -119.4960, "stores_count": 52},
            {"city": "Abbotsford", "postal_code": "V2S 1B1", "fsa": "V2S", "lat": 49.0504, "lon": -122.3045, "stores_count": 44},
            {"city": "Nanaimo", "postal_code": "V9R 5H1", "fsa": "V9R", "lat": 49.1659, "lon": -123.9401, "stores_count": 36},
            {"city": "Kamloops", "postal_code": "V2C 1A1", "fsa": "V2C", "lat": 50.6745, "lon": -120.3273, "stores_count": 34},
        ],
        "key_banners": ["Save-On-Foods", "Choices Markets", "No Frills", "Superstore", "Walmart", "Thrifty Foods", "FreshCo", "T&T Supermarket", "Buy-Low Foods", "Costco"]
    },
    "Canada Wide": {
        "province_code": "CA",
        "description": "Toronto, Montreal, Ottawa, Winnipeg, Halifax & National coverage",
        "cities": [
            {"city": "Toronto", "postal_code": "M5V 2T6", "fsa": "M5V", "lat": 43.6532, "lon": -79.3832, "stores_count": 310},
            {"city": "Montreal", "postal_code": "H2X 1Y4", "fsa": "H2X", "lat": 45.5017, "lon": -73.5673, "stores_count": 275},
            {"city": "Ottawa", "postal_code": "K1P 1J1", "fsa": "K1P", "lat": 45.4215, "lon": -75.6972, "stores_count": 96},
            {"city": "Winnipeg", "postal_code": "R3C 0V8", "fsa": "R3C", "lat": 49.8951, "lon": -97.1384, "stores_count": 76},
            {"city": "Saskatoon", "postal_code": "S7K 0J5", "fsa": "S7K", "lat": 52.1332, "lon": -106.6700, "stores_count": 48},
            {"city": "Halifax", "postal_code": "B3J 1S9", "fsa": "B3J", "lat": 44.6488, "lon": -63.5752, "stores_count": 42},
        ],
        "key_banners": ["Metro", "Loblaws", "Food Basics", "Maxi", "IGA", "Provigo", "Sobeys", "Walmart", "No Frills", "Farm Boy"]
    }
}

# Banner branding styling & themes for UI display
BANNER_THEMES = {
    "No Frills": {"bg": "bg-yellow-400", "text": "text-yellow-950", "badge": "Won't Be Beat", "border": "border-yellow-400/40"},
    "Real Canadian Superstore": {"bg": "bg-amber-600", "text": "text-white", "badge": "PC Optimum", "border": "border-amber-500/40"},
    "Superstore": {"bg": "bg-amber-600", "text": "text-white", "badge": "PC Optimum", "border": "border-amber-500/40"},
    "Walmart": {"bg": "bg-blue-600", "text": "text-white", "badge": "Rollback", "border": "border-blue-500/40"},
    "Save-On-Foods": {"bg": "bg-emerald-600", "text": "text-white", "badge": "More Rewards", "border": "border-emerald-500/40"},
    "Safeway": {"bg": "bg-rose-700", "text": "text-white", "badge": "Scene+", "border": "border-rose-600/40"},
    "Sobeys": {"bg": "bg-emerald-700", "text": "text-white", "badge": "Scene+", "border": "border-emerald-600/40"},
    "FreshCo": {"bg": "bg-lime-600", "text": "text-white", "badge": "Price Match", "border": "border-lime-500/40"},
    "Calgary Co-op": {"bg": "bg-red-600", "text": "text-white", "badge": "Member Dividend", "border": "border-red-500/40"},
    "Choices Markets": {"bg": "bg-teal-700", "text": "text-white", "badge": "100% BC Local", "border": "border-teal-500/40"},
    "Thrifty Foods": {"bg": "bg-emerald-800", "text": "text-white", "badge": "Scene+ Rewards", "border": "border-emerald-700/40"},
    "Buy-Low Foods": {"bg": "bg-orange-600", "text": "text-white", "badge": "Low Price Guarantee", "border": "border-orange-500/40"},
    "T&T Supermarket": {"bg": "bg-emerald-600", "text": "text-white", "badge": "Asian Fresh Deals", "border": "border-emerald-500/40"},
    "H Mart": {"bg": "bg-red-700", "text": "text-white", "badge": "Korean & Asian", "border": "border-red-600/40"},
    "Metro": {"bg": "bg-red-700", "text": "text-white", "badge": "Moi Rewards", "border": "border-red-600/40"},
    "Food Basics": {"bg": "bg-emerald-600", "text": "text-white", "badge": "Always More for Less", "border": "border-emerald-500/40"},
    "Costco": {"bg": "bg-blue-700", "text": "text-white", "badge": "Member Savings", "border": "border-blue-600/40"},
    "Giant Tiger": {"bg": "bg-amber-500", "text": "text-slate-900", "badge": "Tiger Deal", "border": "border-amber-400/40"},
    "London Drugs": {"bg": "bg-blue-800", "text": "text-white", "badge": "Western Canada", "border": "border-blue-700/40"},
    "Fruiticana": {"bg": "bg-orange-500", "text": "text-white", "badge": "Farm Direct", "border": "border-orange-400/40"},
    "Community Natural Foods": {"bg": "bg-green-700", "text": "text-white", "badge": "Organic Alberta", "border": "border-green-600/40"},
    "Country Grocer": {"bg": "bg-emerald-700", "text": "text-white", "badge": "Island Grown", "border": "border-emerald-600/40"},
    "Fairway Markets": {"bg": "bg-red-600", "text": "text-white", "badge": "Local Island", "border": "border-red-500/40"},
}

DEFAULT_BANNER_THEME = {"bg": "bg-slate-700", "text": "text-white", "badge": "Weekly Special", "border": "border-slate-600/40"}

# In-memory flyer and deals caches (TTL: 1 hour)
_FLYERS_CACHE: Dict[str, Dict[str, Any]] = {}
_FLYER_ITEMS_CACHE: Dict[int, Dict[str, Any]] = {}


def clean_postal_code(raw: str) -> str:
    """Standardizes postal code to uppercase 6-character alphanumeric without spaces."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(raw)).upper()
    return cleaned


def resolve_location_to_postal_code(query: str) -> str:
    """
    Resolves a city name (e.g. 'Vancouver', 'Calgary', 'Edmonton', 'Kelowna')
    or postal code to a valid Canadian postal code string.
    Defaults to Edmonton (T5K2X4).
    """
    clean_q = str(query).strip().lower()

    # Check if direct postal code
    cleaned_pc = clean_postal_code(clean_q)
    if len(cleaned_pc) == 6 or (len(cleaned_pc) == 3 and cleaned_pc[0] in "ABCEGHJKLMNPRSTVXY"):
        return cleaned_pc

    # Check city names across Alberta, BC, and Canada Wide
    for reg_data in SUPPORTED_REGIONS.values():
        for c in reg_data["cities"]:
            if c["city"].lower() in clean_q or clean_q in c["city"].lower():
                return clean_postal_code(c["postal_code"])

    # Default fallback: Edmonton
    return "T5K2X4"


def get_city_for_postal_code(postal_code_or_city: str) -> Dict[str, Any]:
    """Finds matching city and province info for given postal code or city name."""
    query_str = str(postal_code_or_city).strip().lower()

    # First check direct city names across supported regions
    for reg_name, reg_data in SUPPORTED_REGIONS.items():
        for c in reg_data["cities"]:
            if c["city"].lower() == query_str or c["city"].lower() in query_str or query_str in c["city"].lower():
                return {
                    "city": c["city"],
                    "province": reg_name,
                    "province_code": reg_data["province_code"],
                    "postal_code": c["postal_code"],
                    "lat": c["lat"],
                    "lon": c["lon"]
                }

    # Resolve to postal code / FSA
    clean_pc = resolve_location_to_postal_code(postal_code_or_city)
    clean = clean_postal_code(clean_pc)
    fsa = clean[:3] if len(clean) >= 3 else "T5K"

    for reg_name, reg_data in SUPPORTED_REGIONS.items():
        for c in reg_data["cities"]:
            if c["fsa"] == fsa or clean_postal_code(c["postal_code"]) == clean:
                return {
                    "city": c["city"],
                    "province": reg_name,
                    "province_code": reg_data["province_code"],
                    "postal_code": c["postal_code"],
                    "lat": c["lat"],
                    "lon": c["lon"]
                }

    # First letter fallback
    first = clean[0] if clean else "T"
    if first == "T":
        return {"city": "Alberta Region", "province": "Alberta", "province_code": "AB", "postal_code": clean_pc, "lat": 53.5444, "lon": -113.4909}
    elif first == "V":
        return {"city": "British Columbia Region", "province": "British Columbia", "province_code": "BC", "postal_code": clean_pc, "lat": 49.2827, "lon": -123.1207}
    else:
        return {"city": "Canada", "province": "Canada Wide", "province_code": "CA", "postal_code": clean_pc, "lat": 43.6532, "lon": -79.3832}


def _today() -> str:
    return local_today().isoformat()


def fetch_live_flyers(postal_code_or_city: str = "T5K2X4") -> List[Dict[str, Any]]:
    """Returns flyers on file whose validity window includes today."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.id, f.banner, f.title, f.total_pages, f.valid_from, f.valid_to, f.badge_text,
               (SELECT COUNT(*) FROM flyer_deals d WHERE d.flyer_id = f.id) AS deals_count
        FROM flyers f
        WHERE f.valid_from <= ? AND f.valid_to >= ?
        ORDER BY f.banner
    """, (_today(), _today()))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    flyers = []
    for r in rows:
        theme = BANNER_THEMES.get(r["banner"], DEFAULT_BANNER_THEME)
        flyers.append({
            "id": r["id"],
            "merchant": r["banner"],
            "banner": r["banner"],
            "title": r["title"],
            "valid_from": r["valid_from"],
            "valid_to": r["valid_to"],
            "total_pages": r["total_pages"],
            "thumbnail_url": None,
            "merchant_logo": None,
            "badge_text": r["badge_text"] or theme["badge"],
            "theme": theme,
            "deals_count": r["deals_count"],
            "is_live": True,
        })
    return flyers


def fetch_flyer_deals(flyer_id: int) -> List[Dict[str, Any]]:
    """Returns the deals recorded for a flyer."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.id, COALESCE(d.item_name, d.title) AS name, d.sale_price, d.original_price,
               d.discount_text, f.valid_from, f.valid_to
        FROM flyer_deals d
        JOIN flyers f ON f.id = d.flyer_id
        WHERE d.flyer_id = ?
        ORDER BY d.page_number, d.sale_price
    """, (flyer_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "brand": "",
            "price": r["sale_price"],
            "price_display": f"${r['sale_price']:.2f}",
            "cutout_image_url": None,
            "valid_from": r["valid_from"],
            "valid_to": r["valid_to"],
            "discount_text": r["discount_text"] or "Flyer Special",
        }
        for r in rows
    ]


def search_flyer_items(query: str, postal_code_or_city: str = "T5K2X4") -> List[Dict[str, Any]]:
    """Searches deals in currently valid flyers by item name."""
    q = query.strip()
    if not q:
        return []
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.id, COALESCE(d.item_name, d.title) AS name, f.banner, d.sale_price, d.original_price,
               d.discount_text, f.valid_from, f.valid_to
        FROM flyer_deals d
        JOIN flyers f ON f.id = d.flyer_id
        WHERE f.valid_from <= ? AND f.valid_to >= ?
          AND (d.title LIKE ? OR d.item_name LIKE ?)
        ORDER BY d.sale_price
    """, (_today(), _today(), f"%{q}%", f"%{q}%"))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "merchant": r["banner"],
            "current_price": r["sale_price"],
            "original_price": r["original_price"],
            "pre_price_text": None,
            "post_price_text": None,
            "image_url": None,
            "valid_from": r["valid_from"],
            "valid_to": r["valid_to"],
            "sale_story": r["discount_text"],
            "theme": BANNER_THEMES.get(r["banner"], DEFAULT_BANNER_THEME),
        }
        for r in rows
    ]
