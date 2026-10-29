# SmartCart

Grocery price comparison and trip planning for the Edmonton area, built on prices that local shoppers report.

> **Status:** closed beta, Edmonton metro only. Not yet deployed from this branch. The roadmap is in [`docs/PROGRESS.md`](docs/PROGRESS.md), and the reasons behind the main choices are in [`docs/adr/`](docs/adr/).

## Why SmartCart

Canadian grocery prices have experienced persistent inflation across core household staples (poultry, dairy, cooking oil, pantry staples). While households actively search for deals across competing supermarket chains—such as **No Frills, Real Canadian Superstore, Walmart, Sobeys, Metro, Save-On-Foods, and FreshCo**—manually comparing weekly circulars across multiple stores is tedious and inefficient.

Furthermore, naive price-chasing frequently leads to **negative net savings**: driving an extra 18 kilometers to save $3.00 on cheese often costs $4.50 in vehicle fuel and depreciation.

**SmartCart** models grocery shopping as a **constrained combinatorial optimization problem** (a variant of the multi-depot Traveling Salesperson Problem combined with multi-objective knapsack constraints). It factors in:
1. Normalized unit pricing ($\$/100\text{g}$, $\$/100\text{mL}$, $\$/\text{kg}$, $\$/\text{unit}$).
2. Live provincial fuel pricing ($\$1.49/\text{L}$ in AB, $\$1.82/\text{L}$ in BC).
3. Geocoded Haversine road travel distance matrices.
4. Guaranteed inventory stock availability vs. multi-stop split trips.

## Where the data comes from

SmartCart is in a **closed beta for the Edmonton metro area**. It never shows invented prices: when it has no recent price for an item, it says so.

| Data | Source | Notes |
| :--- | :--- | :--- |
| **Store locations** | OpenStreetMap via the Overpass API (`scripts/import_osm_stores.py`) | About 200 supermarkets across Edmonton, St. Albert, Sherwood Park, Spruce Grove, Leduc, Beaumont and Fort Saskatchewan. © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright). |
| **Shelf prices** | Crowdsourced `price_observations` (receipts, in-store checks); later a licensed feed | `store_inventory` is a cache of the median price from the last 30 days, with source, observation count and last-seen date. |
| **Flyers** | Entered by an admin (licensed feed planned) | Only flyers whose validity window covers today are shown. |
| **Product nutrition** | Open Food Facts | Looked up by barcode. |
| **Fuel price** | Edmonton average from cheapgasedmonton.ca, with a provincial benchmark as fallback | Used for the travel-cost part of the optimizer. |

To refresh store locations, run `python scripts/import_osm_stores.py`. To load prices you've collected, run `python scripts/import_prices.py prices.csv` (the column format is in the script).

## How the trip optimizer works

The optimization engine solves for the most cost-effective shopping strategy given a user's location (Canadian postal code or coordinates), search radius $R$, and requested grocery list $B = \{i_1, i_2, \dots, i_m\}$.

```
Given:
  S = {s_1, s_2, ..., s_k}  (Set of stores within radius R)
  P(i, s)                   (Price of item i at store s)
  D(s_a, s_b)               (Haversine travel distance between locations)
  GasPrice                  (Provincial fuel rate in $/L)
  FuelConsumptionRate       (9.5 L / 100 km typical vehicle)
```

### The Three Generated Plans

| Strategy | Algorithmic Formulation | Primary Benefit |
| :--- | :--- | :--- |
| **Plan 1: Maximum Net Saver** | Explores candidate store combinations of size $k \in \{1, 2, 3\}$. Solves exact shortest Hamiltonian path (TSP) for the store subset and computes fuel penalty: $\text{Fuel} = D \times \frac{9.5}{100} \times \text{GasPrice}$. Evaluates net out-of-pocket: $\min \left( \sum \min_{s} P(i, s) + \text{Fuel} \right)$. | Lowest overall out-of-pocket cost. |
| **Plan 2: Single-Store Run** | Evaluates all single stores $s \in S$. Finds the single location that minimizes $\sum_{i \in B} P(i, s) + \text{Fuel}(2 \times D(\text{Home}, s))$. | Maximum convenience with 1 stop. |
| **Plan 3: Full Basket Coverage** | Filters candidate stores to those with a recent reported price for every item in the basket. | 0% stockout risk. |

## Architecture

```mermaid
flowchart LR
    PWA["web/ React PWA<br/>(Cloudflare Pages)"] -->|HTTPS + Supabase JWT| API["FastAPI API<br/>smartcart/"]
    PWA -->|magic-link sign-in| Auth["Supabase Auth"]
    API -->|verify JWT via JWKS| Auth
    API --> DB[("Postgres (Supabase)<br/>SQLite locally")]
    Worker["smartcart.worker<br/>price cache + gas + alerts"] --> DB
    API --> OFF["Open Food Facts"]
    Import["scripts/import_osm_stores.py"] -->|OpenStreetMap| Data["smartcart/data/*.json"]
```

| Area | Where |
| :--- | :--- |
| API app, legacy endpoints | `smartcart/main.py` |
| Prices, accounts, personal data, admin | `smartcart/routers/` |
| Auth (Supabase JWT) | `smartcart/auth.py` |
| DB connection layer, price aggregation | `smartcart/database.py` |
| Schema migrations | `smartcart/migrations/` (Alembic) |
| Settings | `smartcart/config.py`, `.env.example` |
| Optimizer, parser, unit normalizer | `smartcart/optimizer.py`, `parser.py`, `normalizer.py` |
| PWA | `web/` |
| Test-only synthetic data | `tests/fixtures/` |

## Local development

Requirements: Python 3.12, Node 22+, and Docker (optional, for Postgres tests).

```bash
# API
python3.12 -m venv venv
venv/bin/pip install -r requirements-dev.txt
cp .env.example .env              # every setting is optional locally
venv/bin/python -m uvicorn smartcart.main:app --reload --port 8000
# Creates/migrates smartcart.db and loads the Edmonton stores on startup.

# PWA (second terminal)
cd web
npm install
cp .env.example .env.local        # add Supabase keys to enable accounts
npm run dev                       # http://localhost:5173, proxies /api to :8000
```

Useful commands:

```bash
venv/bin/python -m smartcart.database --purge-unsourced   # one-time: remove prototype demo data
venv/bin/python scripts/import_osm_stores.py              # refresh store locations from OpenStreetMap
venv/bin/python scripts/import_prices.py prices.csv       # load prices you collected (format in the script)
venv/bin/alembic revision -m "describe change"            # new migration (edit it by hand)
```

## Tests

```bash
venv/bin/ruff check .
venv/bin/python -m pytest -q                              # SQLite
docker run -d --name smartcart-pg-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=smartcart_test -p 55432:5432 postgres:17-alpine
SMARTCART_TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/smartcart_test venv/bin/python -m pytest -q
cd web && npm test && npm run build
```

CI (`.github/workflows/ci.yml`) runs lint, the API tests on both databases, the Docker build, and the web tests and build.

## Deployment

- **API:** `Dockerfile` (non-root, `/healthz` health check). `render.yaml` defines the web service and worker with auto-deploy off; secrets are set in the dashboard. In production set `SMARTCART_RUN_SCHEDULER=false` on the web service and run `python -m smartcart.worker` separately, or use `python -m smartcart.scheduler_once` from a cron job.
- **PWA:** `cd web && npm run build`, then host `web/dist` as a static site with SPA fallback. Set `VITE_API_URL`, `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` at build time, and add the site's origin to `SMARTCART_CORS_ORIGINS`.

## Legal

Draft privacy policy, terms and pricing explainer are in `web/src/legal/`. They need legal review before launch; see [`docs/legal/README.md`](docs/legal/README.md).

Store locations © OpenStreetMap contributors (ODbL). Product data from Open Food Facts (ODbL).
