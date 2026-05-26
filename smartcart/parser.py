"""
SmartCart Natural Language & Recipe Ingredient Parser
Extracts ingredient names, quantities, units, and preparation states from unstructured text.
"""

import re
from fractions import Fraction
from typing import List, Dict, Any, Optional

UNIT_MAP = {
    "kg": "kg", "kilogram": "kg", "kilograms": "kg", "kilos": "kg",
    "g": "g", "gram": "g", "grams": "g",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "l": "L", "liter": "L", "litre": "L", "liters": "L", "litres": "L",
    "ml": "ml", "milliliter": "ml", "millilitre": "ml", "mls": "ml",
    "cup": "cup", "cups": "cup",
    "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "fl oz": "fl oz", "fluid ounce": "fl oz",
    "can": "can", "cans": "can",
    "bag": "bag", "bags": "bag",
    "pack": "pack", "packs": "pack", "package": "pack", "packages": "pack",
    "box": "box", "boxes": "box",
    "block": "block", "blocks": "block",
    "loaf": "loaf", "loaves": "loaf",
    "head": "head", "heads": "head",
    "bunch": "bunch", "bunches": "bunch",
    "dozen": "dozen",
    "clove": "clove", "cloves": "clove",
    "slice": "slice", "slices": "slice",
    "unit": "unit", "units": "unit", "piece": "unit", "pieces": "unit",
}

PREP_WORDS = {
    "diced", "chopped", "minced", "sliced", "crushed", "grated", "shredded",
    "peeled", "melted", "softened", "beaten", "cooked", "uncooked", "fresh",
    "boneless", "skinless", "ground", "lean", "coarsely", "finely", "to taste",
    "optional", "for serving", "room temperature", "divided", "large", "medium", "small"
}

def parse_number(num_str: str) -> float:
    num_str = num_str.strip()
    if not num_str:
        return 1.0
    try:
        if " " in num_str:
            parts = num_str.split()
            whole = float(parts[0])
            frac = float(Fraction(parts[1]))
            return whole + frac
        elif "/" in num_str:
            return float(Fraction(num_str))
        else:
            return float(num_str)
    except Exception:
        return 1.0

def parse_ingredient_line(line: str) -> Optional[Dict[str, Any]]:
    text = line.strip()
    text = re.sub(r"^[\*\-\•]\s*", "", text).strip()
    text = re.sub(r"^\d+[\.\)]\s*", "", text).strip()
    if not text or len(text) < 2:
        return None

    notes = []
    parentheses = re.findall(r"\((.*?)\)", text)
    for p in parentheses:
        notes.append(p)
    text = re.sub(r"\(.*?\)", "", text).strip()

    qty_pattern = r"^(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)\s*"
    qty_match = re.match(qty_pattern, text)
    quantity = 1.0
    if qty_match:
        quantity = parse_number(qty_match.group(1))
        text = text[qty_match.end():].strip()

    words = text.split()
    unit = None
    if words:
        if len(words) >= 2 and f"{words[0].lower()} {words[1].lower()}" in UNIT_MAP:
            unit = UNIT_MAP[f"{words[0].lower()} {words[1].lower()}"]
            words = words[2:]
        elif words[0].lower() in UNIT_MAP:
            unit = UNIT_MAP[words[0].lower()]
            words = words[1:]

    cleaned_name_words = []
    for w in words:
        clean_w = re.sub(r"[^\w\-]", "", w)
        if clean_w.lower() in PREP_WORDS:
            notes.append(clean_w.lower())
        elif clean_w:
            cleaned_name_words.append(clean_w)

    ingredient_name = " ".join(cleaned_name_words)
    if not ingredient_name:
        ingredient_name = " ".join(words)

    return {
        "raw_text": line.strip(),
        "name": ingredient_name.strip(),
        "quantity": quantity,
        "unit": unit or "unit",
        "notes": ", ".join(notes) if notes else None
    }

def parse_recipe_text(text: str) -> List[Dict[str, Any]]:
    results = []
    if "->" in text or "=>" in text:
        parts = re.split(r"\->|=>", text, maxsplit=1)
        text = parts[1]

    lines = text.split("\n")
    if len(lines) == 1 and "," in text:
        candidate_items = [item.strip() for item in text.split(",") if item.strip()]
    else:
        candidate_items = [line.strip() for line in lines if line.strip()]

    for item in candidate_items:
        parsed = parse_ingredient_line(item)
        if parsed and parsed["name"]:
            results.append(parsed)

    return results
