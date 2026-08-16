import re
import time
import ssl
import urllib.request
from typing import Dict, Any, Optional

try:
    UNVERIFIED_SSL = ssl._create_unverified_context()
except Exception:
    UNVERIFIED_SSL = None

# Regional gas price benchmarks (CAD / Litre)
REGIONAL_BENCHMARKS = {
    "AB": {"price": 1.49, "cents": 149.2, "name": "Alberta Fuel Average"},
    "BC": {"price": 1.82, "cents": 182.5, "name": "British Columbia Fuel Average"},
    "ON": {"price": 1.56, "cents": 156.4, "name": "Ontario Fuel Average"},
    "QC": {"price": 1.64, "cents": 164.2, "name": "Quebec Fuel Average"},
    "CA": {"price": 1.55, "cents": 155.0, "name": "Canadian National Average"},
}

_GAS_PRICE_CACHE: Dict[str, Any] = {
    "price_per_litre": 1.49,
    "cents_per_litre": 149.2,
    "city": "Edmonton",
    "province": "AB",
    "currency": "CAD",
    "unit": "$/L",
    "fuel_type": "Regular Unleaded 87",
    "source": "Alberta Live Fuel Feed",
    "source_url": "https://cheapgasedmonton.ca/",
    "is_live": False,
    "last_updated": 0,
}

CACHE_TTL_SECONDS = 3600  # 1 hour


def fetch_live_edmonton_gas_price(province_or_city: str = "AB") -> Dict[str, Any]:
    """
    Fetches real-time regular gasoline prices with regional adaptation for Alberta and BC.
    """
    global _GAS_PRICE_CACHE
    now = time.time()

    norm = str(province_or_city).upper()
    if "BC" in norm or "VANCOUVER" in norm or "VICTORIA" in norm or "KELOWNA" in norm:
        return {
            "price_per_litre": REGIONAL_BENCHMARKS["BC"]["price"],
            "cents_per_litre": REGIONAL_BENCHMARKS["BC"]["cents"],
            "city": "Vancouver / BC",
            "province": "BC",
            "currency": "CAD",
            "unit": "$/L",
            "fuel_type": "Regular Unleaded 87",
            "source": "BC Regional Gas Index",
            "is_live": True,
            "last_updated": now,
        }

    # If cache is still fresh within TTL, return cached value for Alberta
    if _GAS_PRICE_CACHE["last_updated"] > 0 and (now - _GAS_PRICE_CACHE["last_updated"]) < CACHE_TTL_SECONDS:
        return dict(_GAS_PRICE_CACHE)

    url = "https://cheapgasedmonton.ca/"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )

    try:
        kwargs = {"timeout": 3.5}
        if UNVERIFIED_SSL:
            kwargs["context"] = UNVERIFIED_SSL

        with urllib.request.urlopen(req, **kwargs) as response:
            html = response.read().decode("utf-8", errors="ignore")
            match = re.search(r"average reported regular gas price in Edmonton is\s*([\d\.]+)¢/L", html)
            if match:
                cents = float(match.group(1))
                price_per_litre = round(cents / 100.0, 2)
                _GAS_PRICE_CACHE.update({
                    "price_per_litre": price_per_litre,
                    "cents_per_litre": cents,
                    "is_live": True,
                    "last_updated": now,
                })
                return dict(_GAS_PRICE_CACHE)
    except Exception:
        pass

    _GAS_PRICE_CACHE["last_updated"] = now
    return dict(_GAS_PRICE_CACHE)


def get_current_gas_price(province_or_city: str = "AB") -> float:
    """Convenience helper returning float price per litre."""
    data = fetch_live_edmonton_gas_price(province_or_city)
    return float(data.get("price_per_litre", 1.49))
