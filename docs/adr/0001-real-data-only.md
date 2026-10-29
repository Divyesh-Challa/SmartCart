# 0001: Show only sourced data; never invent prices

**Status:** Accepted (2026-10-28)

## Context
The prototype generated 3,524 fictional stores, random shelf prices, random weekly "promotions", fabricated nutrition values and placeholder brands. Shown to the public, these would mislead shoppers and risk breaching the Competition Act's rules on misleading representations.

## Decision
Every user-facing value must have a real source (OpenStreetMap, Open Food Facts, a flyer on file, or shopper reports) and, for prices, a date. When data is missing, the product says so. Synthetic data exists only in `tests/fixtures/` and is never loaded into an app database.

## Consequences
- At launch the optimizer has little data, and the product depends on collecting reports.
- The UI needs empty states ("not enough price data yet") and freshness labels everywhere.
- Code review checks for fallback values that look like data (default prices, distances, brands, dates).
