# 0003: Edmonton-only beta with OpenStreetMap store data

**Status:** Accepted (2026-10-28)

## Context
Crowdsourced prices only work when enough reports land on the same stores. Spreading thin across Canada would leave every area empty.

## Decision
Launch in the Edmonton metro area. Store locations come from OpenStreetMap through the Overpass API (`scripts/import_osm_stores.py`), are committed as `smartcart/data/edmonton_stores.json`, and are upserted on startup by `osm_id`. Attribution ("© OpenStreetMap contributors", ODbL) is shown in the app.

## Consequences
- About half of OSM entries lack a street address. Directions use coordinates instead.
- Some city names are inferred (flagged `city_inferred`).
- Expanding means adding a region to the importer and re-running it.
