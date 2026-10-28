# 0002: Prices from crowdsourced observations, cached as 30-day medians

**Status:** Accepted (2026-10-28)

## Context
No affordable licensed shelf-price feed exists for a solo beta. Flyers cover only sale items.

## Decision
- Raw reports go into `price_observations`: store, product or UPC, price, observed date, source, submitter, trust score and status.
- `store_inventory` is a derived cache: the median of accepted observations from the last 30 days, with source, count and last-seen date. The optimizer and search read only the cache.
- New reports more than 3× off the current median, or from accounts with low trust, are held as `pending` for admin review. Moderation adjusts the submitter's trust score.
- There's a per-user daily cap and a per-account rate limit.

## Alternatives considered
- Licensed feed only: costly and slow to sign. Kept as a future `licensed_feed` source.
- Latest report wins: too easy to manipulate. The median resists outliers.

## Consequences
- One bad report can't move a price that already has two or more reports, though a store's first report is accepted as-is (unless the account has low trust).
- Recomputing a single (store, product) pair after each report keeps writes cheap.
