# 0004: Alembic-managed schema; Postgres in production, SQLite locally

**Status:** Accepted (2026-10-28)

## Context
The prototype used a SQLite file on Render's free tier, whose disk is wiped on each deploy. The code uses raw SQL throughout (~90 queries).

## Decision
- The schema lives in Alembic migrations (`smartcart/migrations`). The baseline is safe to run on old databases.
- `get_connection()` returns `sqlite3` locally, and for Postgres a thin wrapper that keeps the same API: `?` placeholders become `%s`, `LIKE` becomes `ILIKE` (case-insensitive like SQLite), and `lastrowid` comes from `RETURNING id`.
- SQL must be portable: `ON CONFLICT` upserts, no `printf`/`datetime('now')`, no scalar `MIN`/`MAX`.
- CI runs the full test suite on both databases.

## Alternatives considered
A full SQLAlchemy ORM rewrite: cleaner long term, but a much larger change with higher regression risk right now.

## Consequences
- New SQL must be checked against Postgres (CI enforces this).
- Timestamps compared as strings are stored as ISO-8601 text on both databases.
