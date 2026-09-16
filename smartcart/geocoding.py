"""
SmartCart Geocoding & Postal Code Resolution Module
Provides local forward postal code lookup for Canadian Postal Codes (FSAs)
enabling dynamic, zero-cost distance and store proximity calculations without paid APIs.
"""

import re
from typing import Dict, Any, Optional

CANADIAN_PROVINCE_PREFIXES = {
    "A": "Newfoundland and Labrador",
    "B": "Nova Scotia",
    "C": "Prince Edward Island",
    "E": "New Brunswick",
    "G": "Eastern Quebec",
    "H": "Montreal Metropolitan",
    "J": "Western Quebec",
    "K": "Eastern Ontario / Ottawa",
    "L": "Central Ontario",
    "M": "Toronto",
    "N": "Southwestern Ontario",
    "P": "Northern Ontario",
    "R": "Manitoba",
    "S": "Saskatchewan",
    "T": "Alberta",
    "V": "British Columbia",
    "X": "Northwest Territories & Nunavut",
    "Y": "Yukon",
}

EDMONTON_FSA_TABLE = {
    "T5J": {"name": "Downtown / Government Centre", "lat": 53.5444, "lon": -113.4909},
    "T5K": {"name": "Oliver / Unity Square", "lat": 53.5398, "lon": -113.5115},
    "T5G": {"name": "Kingsway / Prince Rupert", "lat": 53.5647, "lon": -113.5076},
    "T5L": {"name": "Northwest Edmonton / Calder", "lat": 53.5855, "lon": -113.5413},
    "T5M": {"name": "Westmount / Inglewood", "lat": 53.5593, "lon": -113.5492},
    "T5N": {"name": "Glenora / High Park", "lat": 53.5422, "lon": -113.5492},
    "T5P": {"name": "Mayfield / West Edmonton", "lat": 53.5451, "lon": -113.5936},
    "T5R": {"name": "Rio Terrace / Crestwood", "lat": 53.5132, "lon": -113.5786},
    "T5S": {"name": "Northwest Industrial", "lat": 53.5702, "lon": -113.6331},
    "T5T": {"name": "West Edmonton Mall / Callingwood", "lat": 53.5097, "lon": -113.6288},
    "T5V": {"name": "St. Albert Trail Commercial", "lat": 53.5902, "lon": -113.5841},
    "T5W": {"name": "Highlands / Bellevue", "lat": 53.5672, "lon": -113.4326},
    "T5X": {"name": "Castle Downs / North Edmonton", "lat": 53.6062, "lon": -113.5147},
    "T5Y": {"name": "Clareview / Hermitage", "lat": 53.6012, "lon": -113.4072},
    "T5Z": {"name": "Lake District / Belle Rive", "lat": 53.6182, "lon": -113.4735},
    "T6A": {"name": "Capilano / Forest Heights", "lat": 53.5382, "lon": -113.4251},
    "T6B": {"name": "Ottewell / Gold Bar", "lat": 53.5222, "lon": -113.4241},
    "T6C": {"name": "Bonnie Doon / Cloverdale", "lat": 53.5222, "lon": -113.4711},
    "T6E": {"name": "Old Strathcona / Whyte Ave", "lat": 53.5186, "lon": -113.4988},
    "T6G": {"name": "University of Alberta / Belgravia", "lat": 53.5222, "lon": -113.5251},
    "T6H": {"name": "Southgate / Pleasantview", "lat": 53.4872, "lon": -113.5181},
    "T6J": {"name": "Kaskitayo / Blue Quill", "lat": 53.4612, "lon": -113.5221},
    "T6K": {"name": "Mill Woods West", "lat": 53.4622, "lon": -113.4531},
    "T6L": {"name": "Mill Woods East", "lat": 53.4632, "lon": -113.4091},
    "T6N": {"name": "South Common / Research Park", "lat": 53.4508, "lon": -113.4883},
    "T6R": {"name": "Riverbend / Terwillegar", "lat": 53.4682, "lon": -113.5761},
    "T6T": {"name": "The Meadows / Tamarack", "lat": 53.4632, "lon": -113.3761},
    "T6W": {"name": "Windermere / Heritage Valley", "lat": 53.4252, "lon": -113.5251},
    "T6X": {"name": "Ellerslie / Summerside / 91 St", "lat": 53.4215, "lon": -113.4682},
    "T8N": {"name": "St. Albert", "lat": 53.6331, "lon": -113.6268},
    "T8A": {"name": "Sherwood Park West", "lat": 53.5358, "lon": -113.3182},
    "T8H": {"name": "Sherwood Park North", "lat": 53.5658, "lon": -113.3382},
}

EXACT_POSTAL_CODES = {
    "T5G3E8": {"name": "Real Canadian Superstore - Kingsway", "lat": 53.5606, "lon": -113.5137},
    "T6A0A1": {"name": "Walmart Supercentre - Capilano", "lat": 53.5358, "lon": -113.4182},
    "T6E2A1": {"name": "No Frills - Old Strathcona", "lat": 53.5186, "lon": -113.4988},
    "T5K2X4": {"name": "Safeway - Unity Square", "lat": 53.5469, "lon": -113.5147},
    "T6X1N2": {"name": "Costco Wholesale - 91 St SW", "lat": 53.4215, "lon": -113.4682},
    "T6N1J8": {"name": "Real Canadian Superstore - South Common", "lat": 53.4508, "lon": -113.4883},
}

def clean_postal_code(code: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", code).upper()

def resolve_postal_code(raw_code: str) -> Optional[Dict[str, Any]]:
    cleaned = clean_postal_code(raw_code)
    if not cleaned or len(cleaned) < 3:
        return None

    first_letter = cleaned[0]
    province = CANADIAN_PROVINCE_PREFIXES.get(first_letter, "Unknown Province")

    if len(cleaned) == 6 and cleaned in EXACT_POSTAL_CODES:
        entry = EXACT_POSTAL_CODES[cleaned]
        return {
            "postal_code": f"{cleaned[:3]} {cleaned[3:]}",
            "fsa": cleaned[:3],
            "neighborhood": entry["name"],
            "city": "Edmonton",
            "province": "Alberta",
            "latitude": entry["lat"],
            "longitude": entry["lon"],
            "supported": True,
            "precision": "exact"
        }

    fsa = cleaned[:3]
    if fsa in EDMONTON_FSA_TABLE:
        entry = EDMONTON_FSA_TABLE[fsa]
        formatted_code = f"{cleaned[:3]} {cleaned[3:]}" if len(cleaned) == 6 else fsa
        return {
            "postal_code": formatted_code,
            "fsa": fsa,
            "neighborhood": entry["name"],
            "city": "Edmonton",
            "province": "Alberta",
            "latitude": entry["lat"],
            "longitude": entry["lon"],
            "supported": True,
            "precision": "fsa"
        }

    if first_letter in CANADIAN_PROVINCE_PREFIXES:
        formatted_code = f"{cleaned[:3]} {cleaned[3:]}" if len(cleaned) == 6 else fsa
        return {
            "postal_code": formatted_code,
            "fsa": fsa,
            "neighborhood": province,
            "city": province,
            "province": province,
            "latitude": None,
            "longitude": None,
            "supported": False,
            "message": f"SmartCart is currently in beta for Edmonton, Alberta. Stores in {province} ({fsa}) are coming soon!"
        }

    return None
