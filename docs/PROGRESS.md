# Overnight Build Progress (autonomous run, started 2026-10-28)

The source of truth for resuming work. The full roadmap is in `~/.claude/plans/rustling-jingling-gray.md`.

## Rules for this run
- Only do work that needs no manual input from the owner: no accounts, keys, deploys, spending or legal sign-off.
- Never merge to `main`, because it may auto-deploy to the live Render site. Stack branches and push them.
- Never add synthetic or invented data that users would see.
- Run `venv/bin/python -m pytest -q` before every commit. When DB code changes, also run it against Postgres:
  `docker start smartcart-pg-test` (or `docker run -d --name smartcart-pg-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=smartcart_test -p 55432:5432 postgres:17-alpine`)
  then `SMARTCART_DATABASE_URL=postgresql://postgres:test@localhost:55432/smartcart_test venv/bin/python -m pytest -q`
- Commit and push after each step, and update this file.

## Branches
1. `feat/real-data-foundation`: OSM stores, price observations, fake data moved to tests (pushed)
2. `feat/backend-hardening` (based on 1): Alembic/Postgres, auth, accounts, prices API, admin, security, CI
3. `feat/pwa-frontend` (based on 2): React PWA in `web/`

## Checklist
- [x] Phase 1: real data foundation
- [x] Pinned requirements, rebuilt venv
- [x] Alembic migrations + Postgres support (tests pass on both)
- [x] Barcode lookup without invented prices
- [x] Supabase JWT auth, users table, per-user receipts/alerts/recipe requests
- [x] Price submission API with validation, outlier review, daily cap, rate limit
- [x] Account profile, CASL consent timestamp, export, delete (de-identifies price reports)
- [x] Admin: flyer entry, moderation, upload guard; /api/sync/refresh admin-only
- [x] Security headers, body size limit, CORS, rate limiting, /healthz, logging, Sentry hook, lifespan, standalone worker
- [x] `.env.example`, Dockerfile hardening (non-root, proxy headers), render.yaml/fly.toml for web + worker (no deploy)
- [x] GitHub Actions CI: pytest on SQLite + Postgres service, ruff, web build/test
- [x] Ruff lint pass
- [x] Phase 3: React + Vite + TS PWA in `web/` (branch `feat/pwa-frontend`)
  - [x] Scaffold: Vite, React, TS, Tailwind (compiled), react-router, vite-plugin-pwa, Vitest
  - [x] API client + Supabase auth client (works disabled when env missing)
  - [x] Screens: onboarding/location, list, compare, plan (optimizer), add price, scan, flyers, account, legal pages
  - [x] EN strings in an i18n dictionary (FR later), WCAG basics, empty/error states, freshness labels
  - [x] Tests (Vitest) and a production build
- [x] Phase 5: draft privacy policy, terms and pricing disclaimer in `docs/legal/` (DRAFT, needs lawyer)
- [x] ADRs in `docs/adr/` for the key decisions
- [ ] README update; final summary + tomorrow's setup checklist in this file

## Log
- Phase 2 backend work is committed on `feat/backend-hardening`: 71 tests pass on SQLite and Postgres.
- Deploy configs (.env.example, non-root Dockerfile verified, render.yaml web+worker, scheduler_once) and pyproject/ruff are committed. Next: finish ruff, then CI, then the PWA.
- Ruff clean; CI workflow pushed. Starting the PWA on `feat/pwa-frontend`.
- Compare endpoint fixed (freshness; no invented stores/brands/dates). PWA built in `web/`: 9 screens, 13 Vitest tests, 108 KB gzipped build, smoke-tested against the local API. Legal drafts in `web/src/legal/` (see docs/legal/README.md). ADRs 0001–0006 written. Remaining: README + final summary.
