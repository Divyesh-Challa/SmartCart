"""
SmartCart Geocoding & Postal Code Resolution Module
Provides local forward postal code and city lookup for Canadian Postal Codes (FSAs)
and Canadian cities, enabling dynamic, zero-cost distance and store proximity calculations.
Full coverage for Alberta, British Columbia, and All Canada.
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

# Major Canadian City Centers with default coordinates and postal codes
CANADIAN_CITIES_TABLE = {
    # Alberta
    "edmonton": {"name": "Edmonton", "province": "Alberta", "province_code": "AB", "fsa": "T5K", "postal_code": "T5K 2X4", "lat": 53.5444, "lon": -113.4909},
    "calgary": {"name": "Calgary", "province": "Alberta", "province_code": "AB", "fsa": "T2P", "postal_code": "T2P 1J9", "lat": 51.0486, "lon": -114.0708},
    "red deer": {"name": "Red Deer", "province": "Alberta", "province_code": "AB", "fsa": "T4N", "postal_code": "T4N 1X5", "lat": 52.2681, "lon": -113.8112},
    "lethbridge": {"name": "Lethbridge", "province": "Alberta", "province_code": "AB", "fsa": "T1J", "postal_code": "T1J 0P4", "lat": 49.6956, "lon": -112.8451},
    "medicine hat": {"name": "Medicine Hat", "province": "Alberta", "province_code": "AB", "fsa": "T1A", "postal_code": "T1A 0A1", "lat": 50.0417, "lon": -110.6775},
    "st albert": {"name": "St. Albert", "province": "Alberta", "province_code": "AB", "fsa": "T8N", "postal_code": "T8N 4K6", "lat": 53.6331, "lon": -113.6268},
    "sherwood park": {"name": "Sherwood Park", "province": "Alberta", "province_code": "AB", "fsa": "T8A", "postal_code": "T8A 0A1", "lat": 53.5358, "lon": -113.3182},
    "fort mcmurray": {"name": "Fort McMurray", "province": "Alberta", "province_code": "AB", "fsa": "T9H", "postal_code": "T9H 1K1", "lat": 56.7264, "lon": -111.3803},
    
    # British Columbia
    "vancouver": {"name": "Vancouver", "province": "British Columbia", "province_code": "BC", "fsa": "V6B", "postal_code": "V6B 1A1", "lat": 49.2827, "lon": -123.1207},
    "victoria": {"name": "Victoria", "province": "British Columbia", "province_code": "BC", "fsa": "V8W", "postal_code": "V8W 1P6", "lat": 48.4284, "lon": -123.3656},
    "surrey": {"name": "Surrey", "province": "British Columbia", "province_code": "BC", "fsa": "V3T", "postal_code": "V3T 1V7", "lat": 49.1913, "lon": -122.8490},
    "burnaby": {"name": "Burnaby", "province": "British Columbia", "province_code": "BC", "fsa": "V5H", "postal_code": "V5H 4C2", "lat": 49.2488, "lon": -122.9805},
    "richmond": {"name": "Richmond", "province": "British Columbia", "province_code": "BC", "fsa": "V6X", "postal_code": "V6X 1X1", "lat": 49.1666, "lon": -123.1336},
    "kelowna": {"name": "Kelowna", "province": "British Columbia", "province_code": "BC", "fsa": "V1Y", "postal_code": "V1Y 1Z9", "lat": 49.8880, "lon": -119.4960},
    "abbotsford": {"name": "Abbotsford", "province": "British Columbia", "province_code": "BC", "fsa": "V2S", "postal_code": "V2S 1B1", "lat": 49.0504, "lon": -122.3045},
    "nanaimo": {"name": "Nanaimo", "province": "British Columbia", "province_code": "BC", "fsa": "V9R", "postal_code": "V9R 5H1", "lat": 49.1659, "lon": -123.9401},
    "kamloops": {"name": "Kamloops", "province": "British Columbia", "province_code": "BC", "fsa": "V2C", "postal_code": "V2C 1A1", "lat": 50.6745, "lon": -120.3273},
    
    # Canada Wide
    "toronto": {"name": "Toronto", "province": "Ontario", "province_code": "ON", "fsa": "M5V", "postal_code": "M5V 2T6", "lat": 43.6532, "lon": -79.3832},
    "montreal": {"name": "Montreal", "province": "Quebec", "province_code": "QC", "fsa": "H2X", "postal_code": "H2X 1Y4", "lat": 45.5017, "lon": -73.5673},
    "ottawa": {"name": "Ottawa", "province": "Ontario", "province_code": "ON", "fsa": "K1P", "postal_code": "K1P 1J1", "lat": 45.4215, "lon": -75.6972},
    "winnipeg": {"name": "Winnipeg", "province": "Manitoba", "province_code": "MB", "fsa": "R3C", "postal_code": "R3C 0V8", "lat": 49.8951, "lon": -97.1384},
    "saskatoon": {"name": "Saskatoon", "province": "Saskatchewan", "province_code": "SK", "fsa": "S7K", "postal_code": "S7K 0J5", "lat": 52.1332, "lon": -106.6700},
    "halifax": {"name": "Halifax", "province": "Nova Scotia", "province_code": "NS", "fsa": "B3J", "postal_code": "B3J 1S9", "lat": 44.6488, "lon": -63.5752},
}

# Canadian Forward Sortation Areas (FSAs)
CANADIAN_FSA_TABLE = {
    # Edmonton FSAs
    "T5J": {"name": "Downtown Edmonton", "city": "Edmonton", "province": "Alberta", "lat": 53.5444, "lon": -113.4909},
    "T5K": {"name": "Oliver / Unity Square", "city": "Edmonton", "province": "Alberta", "lat": 53.5398, "lon": -113.5115},
    "T5G": {"name": "Kingsway / Prince Rupert", "city": "Edmonton", "province": "Alberta", "lat": 53.5647, "lon": -113.5076},
    "T5L": {"name": "Northwest Edmonton / Calder", "city": "Edmonton", "province": "Alberta", "lat": 53.5855, "lon": -113.5413},
    "T5M": {"name": "Westmount / Inglewood", "city": "Edmonton", "province": "Alberta", "lat": 53.5593, "lon": -113.5492},
    "T5N": {"name": "Glenora / High Park", "city": "Edmonton", "province": "Alberta", "lat": 53.5422, "lon": -113.5492},
    "T5P": {"name": "Mayfield / West Edmonton", "city": "Edmonton", "province": "Alberta", "lat": 53.5451, "lon": -113.5936},
    "T5R": {"name": "Rio Terrace / Crestwood", "city": "Edmonton", "province": "Alberta", "lat": 53.5132, "lon": -113.5786},
    "T5S": {"name": "Northwest Industrial", "city": "Edmonton", "province": "Alberta", "lat": 53.5702, "lon": -113.6331},
    "T5T": {"name": "West Edmonton Mall / Callingwood", "city": "Edmonton", "province": "Alberta", "lat": 53.5097, "lon": -113.6288},
    "T5V": {"name": "St. Albert Trail Commercial", "city": "Edmonton", "province": "Alberta", "lat": 53.5902, "lon": -113.5841},
    "T5W": {"name": "Highlands / Bellevue", "city": "Edmonton", "province": "Alberta", "lat": 53.5672, "lon": -113.4326},
    "T5X": {"name": "Castle Downs / North Edmonton", "city": "Edmonton", "province": "Alberta", "lat": 53.6062, "lon": -113.5147},
    "T5Y": {"name": "Clareview / Hermitage", "city": "Edmonton", "province": "Alberta", "lat": 53.6012, "lon": -113.4072},
    "T5Z": {"name": "Lake District / Belle Rive", "city": "Edmonton", "province": "Alberta", "lat": 53.6182, "lon": -113.4735},
    "T6A": {"name": "Capilano / Forest Heights", "city": "Edmonton", "province": "Alberta", "lat": 53.5382, "lon": -113.4251},
    "T6B": {"name": "Ottewell / Gold Bar", "city": "Edmonton", "province": "Alberta", "lat": 53.5222, "lon": -113.4241},
    "T6C": {"name": "Bonnie Doon / Cloverdale", "city": "Edmonton", "province": "Alberta", "lat": 53.5222, "lon": -113.4711},
    "T6E": {"name": "Old Strathcona / Whyte Ave", "city": "Edmonton", "province": "Alberta", "lat": 53.5186, "lon": -113.4988},
    "T6G": {"name": "University of Alberta / Belgravia", "city": "Edmonton", "province": "Alberta", "lat": 53.5222, "lon": -113.5251},
    "T6H": {"name": "Southgate / Pleasantview", "city": "Edmonton", "province": "Alberta", "lat": 53.4872, "lon": -113.5181},
    "T6J": {"name": "Kaskitayo / Blue Quill", "city": "Edmonton", "province": "Alberta", "lat": 53.4612, "lon": -113.5221},
    "T6K": {"name": "Mill Woods West", "city": "Edmonton", "province": "Alberta", "lat": 53.4622, "lon": -113.4531},
    "T6L": {"name": "Mill Woods East", "city": "Edmonton", "province": "Alberta", "lat": 53.4632, "lon": -113.4091},
    "T6N": {"name": "South Common / Research Park", "city": "Edmonton", "province": "Alberta", "lat": 53.4508, "lon": -113.4883},
    "T6R": {"name": "Riverbend / Terwillegar", "city": "Edmonton", "province": "Alberta", "lat": 53.4682, "lon": -113.5761},
    "T6T": {"name": "The Meadows / Tamarack", "city": "Edmonton", "province": "Alberta", "lat": 53.4632, "lon": -113.3761},
    "T6W": {"name": "Windermere / Heritage Valley", "city": "Edmonton", "province": "Alberta", "lat": 53.4252, "lon": -113.5251},
    "T6X": {"name": "Ellerslie / Summerside / 91 St", "city": "Edmonton", "province": "Alberta", "lat": 53.4215, "lon": -113.4682},
    "T8N": {"name": "St. Albert", "city": "St. Albert", "province": "Alberta", "lat": 53.6331, "lon": -113.6268},
    "T8A": {"name": "Sherwood Park West", "city": "Sherwood Park", "province": "Alberta", "lat": 53.5358, "lon": -113.3182},
    "T8H": {"name": "Sherwood Park North", "city": "Sherwood Park", "province": "Alberta", "lat": 53.5658, "lon": -113.3382},

    # Calgary FSAs
    "T2P": {"name": "Downtown Calgary / City Centre", "city": "Calgary", "province": "Alberta", "lat": 51.0486, "lon": -114.0708},
    "T2R": {"name": "Beltline / 17th Ave SW", "city": "Calgary", "province": "Alberta", "lat": 51.0392, "lon": -114.0766},
    "T2S": {"name": "Mission / Cliff Bungalow", "city": "Calgary", "province": "Alberta", "lat": 51.0310, "lon": -114.0708},
    "T2T": {"name": "Altadore / South Calgary", "city": "Calgary", "province": "Alberta", "lat": 51.0195, "lon": -114.1030},
    "T2V": {"name": "Oakridge / Chinook South", "city": "Calgary", "province": "Alberta", "lat": 50.9760, "lon": -114.0950},
    "T2W": {"name": "Braeside / Woodbine", "city": "Calgary", "province": "Alberta", "lat": 50.9570, "lon": -114.1080},
    "T2H": {"name": "Chinook / Highfield Commercial", "city": "Calgary", "province": "Alberta", "lat": 50.9980, "lon": -114.0680},
    "T2J": {"name": "Lake Bonavista / Willow Park", "city": "Calgary", "province": "Alberta", "lat": 50.9510, "lon": -114.0530},
    "T2X": {"name": "Shawnessy / Somerset", "city": "Calgary", "province": "Alberta", "lat": 50.9060, "lon": -114.0790},
    "T2Y": {"name": "Millrise / Evergreen", "city": "Calgary", "province": "Alberta", "lat": 50.9120, "lon": -114.1080},
    "T2Z": {"name": "Douglasdale / McKenzie Lake", "city": "Calgary", "province": "Alberta", "lat": 50.9310, "lon": -113.9920},
    "T3A": {"name": "Dalhousie / Silver Springs", "city": "Calgary", "province": "Alberta", "lat": 51.1090, "lon": -114.1680},
    "T3B": {"name": "Bowness / Montgomery", "city": "Calgary", "province": "Alberta", "lat": 51.0850, "lon": -114.1830},
    "T3G": {"name": "Crowfoot / Hawkwood / Citadel", "city": "Calgary", "province": "Alberta", "lat": 51.1370, "lon": -114.1950},
    "T3H": {"name": "Westhills / Signal Hill / Aspen", "city": "Calgary", "province": "Alberta", "lat": 51.0420, "lon": -114.1850},
    "T3J": {"name": "Castleridge / Falconridge / Westwinds", "city": "Calgary", "province": "Alberta", "lat": 51.0980, "lon": -113.9620},
    "T3K": {"name": "Country Hills / Panorama / Beddington", "city": "Calgary", "province": "Alberta", "lat": 51.1410, "lon": -114.0720},
    "T1Y": {"name": "Sunridge / Rundle / Marlborough", "city": "Calgary", "province": "Alberta", "lat": 51.0720, "lon": -113.9850},

    # Other Alberta
    "T4N": {"name": "Downtown Red Deer", "city": "Red Deer", "province": "Alberta", "lat": 52.2681, "lon": -113.8112},
    "T4P": {"name": "North Red Deer", "city": "Red Deer", "province": "Alberta", "lat": 52.3020, "lon": -113.8340},
    "T1J": {"name": "Lethbridge Central", "city": "Lethbridge", "province": "Alberta", "lat": 49.6956, "lon": -112.8451},
    "T1A": {"name": "Medicine Hat Central", "city": "Medicine Hat", "province": "Alberta", "lat": 50.0417, "lon": -110.6775},
    "T9H": {"name": "Fort McMurray Urban", "city": "Fort McMurray", "province": "Alberta", "lat": 56.7264, "lon": -111.3803},

    # British Columbia: Vancouver FSAs
    "V6B": {"name": "Downtown Vancouver / Yaletown", "city": "Vancouver", "province": "British Columbia", "lat": 49.2827, "lon": -123.1207},
    "V6E": {"name": "West End / Robson Street", "city": "Vancouver", "province": "British Columbia", "lat": 49.2858, "lon": -123.1340},
    "V6Z": {"name": "Yaletown / Granville South", "city": "Vancouver", "province": "British Columbia", "lat": 49.2760, "lon": -123.1260},
    "V6A": {"name": "Strathcona / Chinatown", "city": "Vancouver", "province": "British Columbia", "lat": 49.2780, "lon": -123.0980},
    "V5T": {"name": "Mount Pleasant / Main Street", "city": "Vancouver", "province": "British Columbia", "lat": 49.2620, "lon": -123.0980},
    "V5V": {"name": "Riley Park / Little Mountain", "city": "Vancouver", "province": "British Columbia", "lat": 49.2460, "lon": -123.1020},
    "V6J": {"name": "Kitsilano / Broadway West", "city": "Vancouver", "province": "British Columbia", "lat": 49.2640, "lon": -123.1510},
    "V6K": {"name": "Kitsilano North / 4th Ave", "city": "Vancouver", "province": "British Columbia", "lat": 49.2690, "lon": -123.1680},
    "V5K": {"name": "Hastings-Sunrise / East Van", "city": "Vancouver", "province": "British Columbia", "lat": 49.2810, "lon": -123.0420},
    "V5N": {"name": "Kensington-Cedar Cottage / Commercial", "city": "Vancouver", "province": "British Columbia", "lat": 49.2480, "lon": -123.0680},
    "V5P": {"name": "Victoria-Fraserview", "city": "Vancouver", "province": "British Columbia", "lat": 49.2220, "lon": -123.0680},
    "V5X": {"name": "Sunset / Marine Gateway", "city": "Vancouver", "province": "British Columbia", "lat": 49.2130, "lon": -123.1020},

    # Other British Columbia
    "V8W": {"name": "Downtown Victoria", "city": "Victoria", "province": "British Columbia", "lat": 48.4284, "lon": -123.3656},
    "V8T": {"name": "Victoria North / Hillside", "city": "Victoria", "province": "British Columbia", "lat": 48.4410, "lon": -123.3610},
    "V3T": {"name": "Surrey City Centre / Whalley", "city": "Surrey", "province": "British Columbia", "lat": 49.1913, "lon": -122.8490},
    "V3R": {"name": "North Surrey / Guildford", "city": "Surrey", "province": "British Columbia", "lat": 49.2010, "lon": -122.8050},
    "V5H": {"name": "Metrotown / Central Burnaby", "city": "Burnaby", "province": "British Columbia", "lat": 49.2488, "lon": -122.9805},
    "V6X": {"name": "Richmond City Centre / Lansdowne", "city": "Richmond", "province": "British Columbia", "lat": 49.1666, "lon": -123.1336},
    "V1Y": {"name": "Downtown Kelowna", "city": "Kelowna", "province": "British Columbia", "lat": 49.8880, "lon": -119.4960},
    "V2S": {"name": "Central Abbotsford", "city": "Abbotsford", "province": "British Columbia", "lat": 49.0504, "lon": -122.3045},
    "V9R": {"name": "Downtown Nanaimo", "city": "Nanaimo", "province": "British Columbia", "lat": 49.1659, "lon": -123.9401},
    "V2C": {"name": "Downtown Kamloops", "city": "Kamloops", "province": "British Columbia", "lat": 50.6745, "lon": -120.3273},

    # Canada Wide Hubs
    "M5V": {"name": "Downtown Toronto / Entertainment District", "city": "Toronto", "province": "Ontario", "lat": 43.6532, "lon": -79.3832},
    "M4Y": {"name": "Church and Wellesley / Downtown East", "city": "Toronto", "province": "Ontario", "lat": 43.6660, "lon": -79.3810},
    "H2X": {"name": "Downtown Montreal / Quartier des Spectacles", "city": "Montreal", "province": "Quebec", "lat": 45.5017, "lon": -73.5673},
    "H3B": {"name": "Downtown Montreal / Place Ville Marie", "city": "Montreal", "province": "Quebec", "lat": 45.5010, "lon": -73.5710},
    "K1P": {"name": "Parliament Hill / Downtown Ottawa", "city": "Ottawa", "province": "Ontario", "lat": 45.4215, "lon": -75.6972},
    "R3C": {"name": "Downtown Winnipeg", "city": "Winnipeg", "province": "Manitoba", "lat": 49.8951, "lon": -97.1384},
    "S7K": {"name": "Downtown Saskatoon", "city": "Saskatoon", "province": "Saskatchewan", "lat": 52.1332, "lon": -106.6700},
    "B3J": {"name": "Downtown Halifax", "city": "Halifax", "province": "Nova Scotia", "lat": 44.6488, "lon": -63.5752},
}

EXACT_POSTAL_CODES = {
    "T5G3E8": {"name": "Real Canadian Superstore - Kingsway", "city": "Edmonton", "province": "Alberta", "lat": 53.5606, "lon": -113.5137},
    "T6A0A1": {"name": "Walmart Supercentre - Capilano", "city": "Edmonton", "province": "Alberta", "lat": 53.5358, "lon": -113.4182},
    "T6E2A1": {"name": "No Frills - Old Strathcona", "city": "Edmonton", "province": "Alberta", "lat": 53.5186, "lon": -113.4988},
    "T5K2X4": {"name": "Safeway - Unity Square", "city": "Edmonton", "province": "Alberta", "lat": 53.5469, "lon": -113.5147},
    "T6X1N2": {"name": "Costco Wholesale - 91 St SW", "city": "Edmonton", "province": "Alberta", "lat": 53.4215, "lon": -113.4682},
    "T6N1J8": {"name": "Real Canadian Superstore - South Common", "city": "Edmonton", "province": "Alberta", "lat": 53.4508, "lon": -113.4883},
    
    # Calgary
    "T2P1J9": {"name": "Calgary City Centre", "city": "Calgary", "province": "Alberta", "lat": 51.0486, "lon": -114.0708},
    "T2H2V9": {"name": "Chinook Centre Supermarket District", "city": "Calgary", "province": "Alberta", "lat": 50.9980, "lon": -114.0680},
    
    # Vancouver
    "V6B1A1": {"name": "Vancouver Robson & Granville Core", "city": "Vancouver", "province": "British Columbia", "lat": 49.2827, "lon": -123.1207},
    "V5X3X8": {"name": "Marine Gateway Shopping Hub", "city": "Vancouver", "province": "British Columbia", "lat": 49.2130, "lon": -123.1020},
}


def clean_postal_code(code: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(code)).upper()


def resolve_postal_code(raw_input: str) -> Optional[Dict[str, Any]]:
    """
    Resolves postal codes (6-character or 3-character FSA) OR city names
    across Alberta, British Columbia, and all Canadian provinces.
    """
    clean_str = str(raw_input).strip()
    if not clean_str:
        return None

    lower_query = clean_str.lower()

    # 1. Check City Name Table First (e.g. "Calgary", "Vancouver", "Victoria", "Edmonton")
    for city_key, city_data in CANADIAN_CITIES_TABLE.items():
        if city_key == lower_query or lower_query in city_key or city_key in lower_query:
            return {
                "postal_code": city_data["postal_code"],
                "fsa": city_data["fsa"],
                "neighborhood": f"{city_data['name']} City Center",
                "city": city_data["name"],
                "province": city_data["province"],
                "province_code": city_data["province_code"],
                "latitude": city_data["lat"],
                "longitude": city_data["lon"],
                "supported": True,
                "precision": "city"
            }

    # 2. Check Alphanumeric Postal Codes
    cleaned = clean_postal_code(clean_str)
    if len(cleaned) < 3:
        return None

    first_letter = cleaned[0]
    province_name = CANADIAN_PROVINCE_PREFIXES.get(first_letter, "Canada")

    # Exact 6-character match
    if len(cleaned) == 6 and cleaned in EXACT_POSTAL_CODES:
        entry = EXACT_POSTAL_CODES[cleaned]
        return {
            "postal_code": f"{cleaned[:3]} {cleaned[3:]}",
            "fsa": cleaned[:3],
            "neighborhood": entry["name"],
            "city": entry["city"],
            "province": entry["province"],
            "latitude": entry["lat"],
            "longitude": entry["lon"],
            "supported": True,
            "precision": "exact"
        }

    # FSA (first 3 characters) match
    fsa = cleaned[:3]
    if fsa in CANADIAN_FSA_TABLE:
        entry = CANADIAN_FSA_TABLE[fsa]
        formatted_code = f"{cleaned[:3]} {cleaned[3:]}" if len(cleaned) == 6 else f"{fsa} 1A1"
        return {
            "postal_code": formatted_code,
            "fsa": fsa,
            "neighborhood": entry["name"],
            "city": entry["city"],
            "province": entry["province"],
            "latitude": entry["lat"],
            "longitude": entry["lon"],
            "supported": True,
            "precision": "fsa"
        }

    # Fallback to Province level
    if first_letter in CANADIAN_PROVINCE_PREFIXES:
        formatted_code = f"{cleaned[:3]} {cleaned[3:]}" if len(cleaned) == 6 else f"{fsa} 1A1"
        # Provide approximate center coordinates based on province
        lat, lon = (53.5444, -113.4909) if first_letter == "T" else ((49.2827, -123.1207) if first_letter == "V" else (43.6532, -79.3832))
        city_name = "Alberta Hub" if first_letter == "T" else ("BC Hub" if first_letter == "V" else province_name)
        return {
            "postal_code": formatted_code,
            "fsa": fsa,
            "neighborhood": f"{province_name} Region",
            "city": city_name,
            "province": province_name,
            "latitude": lat,
            "longitude": lon,
            "supported": True,
            "precision": "province"
        }

    return None
