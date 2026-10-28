"""Barcode helpers shared by the API, the database layer and import scripts."""

import re


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
