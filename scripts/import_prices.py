"""
Import real price observations from a CSV (e.g. transcribed from receipts or
checked on store shelves) and rebuild the store price cache.

CSV columns (header required):
    store_osm_id   OSM id from smartcart/data/<region>_stores.json, e.g. "way/123456"
    item           Item name as written; matched against the product catalog
    price          Shelf price paid, e.g. 5.99
    observed_at    Date or ISO timestamp the price was seen, e.g. 2026-10-27
    source         receipt | manual            (optional, default: manual)
    is_sale        1 if it was a sale price    (optional, default: 0)
    upc            Barcode, if known           (optional)

Usage:
    python scripts/import_prices.py prices.csv [--submitted-by you@example.com] [--dry-run]
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smartcart.database import (  # noqa: E402
    get_connection,
    init_db,
    record_price_observation,
    refresh_inventory_from_observations,
)
from smartcart.normalizer import match_product_in_catalog  # noqa: E402

ALLOWED_SOURCES = {"receipt", "manual"}


def import_rows(rows, submitted_by=None, dry_run=False):
    conn = get_connection()
    store_ids = {r["osm_id"]: r["id"] for r in conn.execute("SELECT id, osm_id FROM stores WHERE osm_id IS NOT NULL")}
    imported, problems = 0, []

    for line_no, row in enumerate(rows, start=2):
        osm_id = (row.get("store_osm_id") or "").strip()
        item = (row.get("item") or "").strip()
        source = (row.get("source") or "manual").strip().lower()
        try:
            price = float(row.get("price", ""))
        except ValueError:
            problems.append(f"line {line_no}: invalid price {row.get('price')!r}")
            continue
        if osm_id not in store_ids:
            problems.append(f"line {line_no}: unknown store_osm_id {osm_id!r}")
            continue
        if source not in ALLOWED_SOURCES:
            problems.append(f"line {line_no}: source must be one of {sorted(ALLOWED_SOURCES)}")
            continue
        observed_at = (row.get("observed_at") or "").strip()
        if not observed_at:
            problems.append(f"line {line_no}: observed_at is required")
            continue

        product = match_product_in_catalog(item) if item else None
        upc = (row.get("upc") or "").strip() or None
        if not product and not upc:
            problems.append(f"line {line_no}: {item!r} matches no catalog product and has no UPC")
            continue

        if not dry_run:
            record_price_observation(
                conn,
                store_id=store_ids[osm_id],
                price=price,
                source=source,
                observed_at=observed_at,
                product_id=product["id"] if product else None,
                upc=upc,
                raw_item_name=item or None,
                is_sale=(row.get("is_sale") or "0").strip() in ("1", "true", "yes"),
                submitted_by=submitted_by,
            )
        imported += 1

    rebuilt = 0 if dry_run else refresh_inventory_from_observations(conn)
    conn.close()
    return imported, rebuilt, problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path")
    parser.add_argument("--submitted-by")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    init_db()
    with open(args.csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    imported, rebuilt, problems = import_rows(rows, args.submitted_by, args.dry_run)

    for p in problems:
        print(f"skipped {p}", file=sys.stderr)
    verb = "Would import" if args.dry_run else "Imported"
    print(f"{verb} {imported} observations ({len(problems)} skipped); {rebuilt} store prices in cache.")
    return 1 if problems and not imported else 0


if __name__ == "__main__":
    sys.exit(main())
