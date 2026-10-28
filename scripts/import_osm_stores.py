"""
Fetch real grocery store locations from OpenStreetMap (Overpass API) and write
them to smartcart/data/<region>_stores.json.

Store data © OpenStreetMap contributors, available under the Open Database
License (ODbL): https://www.openstreetmap.org/copyright

Usage:
    python scripts/import_osm_stores.py              # Edmonton metro (default)
"""

import argparse
import datetime
import json
import math
import sys
import time
from pathlib import Path

import httpx

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
DATA_DIR = Path(__file__).resolve().parent.parent / "smartcart" / "data"

# (south, west, north, east)
REGIONS = {
    "edmonton": {
        "bbox": (53.25, -113.95, 53.75, -113.20),
        "province": "AB",
        # Municipality centres used to label stores whose OSM entry has no addr:city.
        "municipalities": [
            ("Edmonton", 53.5444, -113.4909),
            ("St. Albert", 53.6331, -113.6268),
            ("Sherwood Park", 53.5358, -113.3182),
            ("Spruce Grove", 53.5450, -113.9008),
            ("Stony Plain", 53.5263, -114.0050),
            ("Leduc", 53.2594, -113.5492),
            ("Beaumont", 53.3572, -113.4147),
            ("Fort Saskatchewan", 53.7128, -113.2133),
        ],
    },
}

# Map OSM brand/name values to the banner names used across SmartCart.
BANNER_ALIASES = {
    "real canadian superstore": "Superstore",
    "superstore": "Superstore",
    "no frills": "No Frills",
    "nofrills": "No Frills",
    "walmart": "Walmart",
    "walmart supercentre": "Walmart",
    "save-on-foods": "Save-On-Foods",
    "save on foods": "Save-On-Foods",
    "safeway": "Safeway",
    "sobeys": "Sobeys",
    "costco": "Costco",
    "freshco": "FreshCo",
    "t&t supermarket": "T&T Supermarket",
    "t & t supermarket": "T&T Supermarket",
    "co-op": "Co-op",
    "calgary co-op": "Calgary Co-op",
    "h&w produce": "H&W Produce",
    "giant tiger": "Giant Tiger",
    "freson bros.": "Freson Bros.",
    "freson bros": "Freson Bros.",
    "italian centre shop": "Italian Centre Shop",
    "lucky 97": "Lucky 97",
    "safeway community market": "Safeway",
    "independent": "Your Independent Grocer",
    "your independent grocer": "Your Independent Grocer",
    "loblaws": "Loblaws",
    "food basics": "Food Basics",
    "save-on": "Save-On-Foods",
    "sunterra market": "Sunterra Market",
    "planet organic": "Planet Organic",
    "whole foods market": "Whole Foods Market",
    "iga": "IGA",
    "wholesale club": "Wholesale Club",
    "real canadian wholesale club": "Wholesale Club",
}

# Mis-tagged in OSM as supermarkets; not grocery stores we can price-compare.
EXCLUDED_BANNERS = {"Dollarama", "Evoolution"}

MEMBERSHIP_BANNERS = {"Costco"}


def build_query(bbox) -> str:
    s, w, n, e = bbox
    b = f"({s},{w},{n},{e})"
    return f"""
[out:json][timeout:90];
(
  nwr["shop"="supermarket"]{b};
  nwr["shop"="wholesale"]["brand"~"Costco",i]{b};
  nwr["shop"="department_store"]["brand"~"Walmart",i]{b};
);
out center tags;
"""


def normalize_banner(tags: dict) -> str:
    for key in ("brand", "name"):
        val = (tags.get(key) or "").strip()
        if not val:
            continue
        low = val.lower()
        if low in BANNER_ALIASES:
            return BANNER_ALIASES[low]
        for alias, banner in BANNER_ALIASES.items():
            # Franchise names like "Craig's No Frills" or "Cliff's IGA".
            if low.startswith(alias) or low.endswith(" " + alias):
                return banner
    return (tags.get("brand") or tags.get("name") or "Independent Grocer").strip()


def format_address(tags: dict) -> str:
    num = tags.get("addr:housenumber", "").strip()
    street = tags.get("addr:street", "").strip()
    unit = tags.get("addr:unit", "").strip()
    if not street:
        return ""
    addr = f"{num} {street}".strip()
    return f"{unit}-{addr}" if unit else addr


def element_to_store(el: dict, province: str):
    tags = el.get("tags", {})
    if el["type"] == "node":
        lat, lon = el.get("lat"), el.get("lon")
    else:
        center = el.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    if lat is None or lon is None:
        return None
    name = (tags.get("name") or "").strip()
    banner = normalize_banner(tags)
    if banner in EXCLUDED_BANNERS:
        return None
    if not name:
        name = banner
    return {
        "osm_id": f"{el['type']}/{el['id']}",
        "name": name,
        "banner": banner,
        "address": format_address(tags),
        "city": (tags.get("addr:city") or "").strip(),
        "province": province,
        "postal_code": (tags.get("addr:postcode") or "").strip().upper(),
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "requires_membership": 1 if banner in MEMBERSHIP_BANNERS else 0,
        "opening_hours": tags.get("opening_hours"),
        "website": tags.get("website") or tags.get("contact:website"),
    }


def _approx_km(lat1, lon1, lat2, lon2) -> float:
    return 111.0 * math.hypot(lat2 - lat1, (lon2 - lon1) * math.cos(math.radians(lat1)))


def infer_missing_cities(stores: list, municipalities: list, town_radius_km: float = 5.0) -> None:
    """
    Label stores lacking addr:city. The first municipality is the core city and
    the default; a surrounding town is only used when the store is within
    town_radius_km of its centre.
    """
    core, towns = municipalities[0], municipalities[1:]
    for st in stores:
        if st["city"] and not st.get("city_inferred"):
            st["city_inferred"] = False
            continue
        city = core[0]
        best = town_radius_km
        for name, lat, lon in towns:
            d = _approx_km(st["latitude"], st["longitude"], lat, lon)
            if d <= best:
                city, best = name, d
        st["city"] = city
        st["city_inferred"] = True


def fetch(region: str) -> dict:
    cfg = REGIONS[region]
    payload = None
    last_err = None
    for attempt in range(2):
        for url in OVERPASS_URLS:
            try:
                resp = httpx.post(
                    url,
                    data={"data": build_query(cfg["bbox"])},
                    headers={"User-Agent": "SmartCart store importer"},
                    timeout=120,
                )
                resp.raise_for_status()
                payload = resp.json()
                break
            except (httpx.HTTPError, ValueError) as e:
                last_err = e
                print(f"Overpass mirror failed ({url}): {e}", file=sys.stderr)
        if payload is not None:
            break
        time.sleep(10)
    if payload is None:
        raise RuntimeError(f"All Overpass mirrors failed: {last_err}")

    stores = []
    seen = set()
    for el in payload.get("elements", []):
        st = element_to_store(el, cfg["province"])
        if st and st["osm_id"] not in seen:
            seen.add(st["osm_id"])
            stores.append(st)
    infer_missing_cities(stores, cfg["municipalities"])
    stores.sort(key=lambda s: (s["banner"], s["name"], s["osm_id"]))

    return {
        "region": region,
        "source": "OpenStreetMap via Overpass API",
        "license": "ODbL 1.0",
        "attribution": "© OpenStreetMap contributors",
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "bbox": cfg["bbox"],
        "stores": stores,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="edmonton", choices=sorted(REGIONS))
    args = parser.parse_args(argv)

    result = fetch(args.region)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"{args.region}_stores.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(result['stores'])} stores to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
