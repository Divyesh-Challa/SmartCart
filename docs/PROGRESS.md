# Build Progress

The source of truth for resuming work. The full roadmap is in `~/.claude/plans/rustling-jingling-gray.md`.

## Working copy
Work happens in `~/Developer/SmartCart`. The old copy in `~/Documents/Projects/SmartCart` sits in iCloud Drive with "Optimize Storage" on, which made file reads time out; it is behind and shouldn't be used.

## Rules
- Never merge to `main`: the old demo on Render (smartcart-9djq.onrender.com) deploys from it. Stack branches and push them.
- Production deploys, spending money, legal sign-off and data agreements need the owner each time.
- Never add synthetic or invented data that users would see. Every price has a source and an `observed_at`.
- Run tests before every commit (`ruff`, `pytest` on SQLite, and Postgres when DB code changes; `npm run lint`, `npm test`, `npm run e2e` in `web/`).
- Secrets live only in gitignored `.env` and `web/.env.local`.

## Branches (stacked, all pushed)
1. `feat/real-data-foundation` (PR #1): OSM stores, price observations, fake data moved to tests
2. `feat/backend-hardening` (PR #2): Alembic/Postgres, Supabase auth, accounts, prices API, admin, security, CI
3. `feat/pwa-frontend` (PR #3): React PWA in `web/`, owner admin
4. `feat/deploy-ready`: one Render service serving the PWA, runtime `/config.js`, deploy script
5. `feat/beta-completion`: list sync, flyer prices in plans, receipt OCR, CSP, chunked body limit, local-calendar dates, Playwright E2E

## Done
- Real data only: 208 Edmonton stores from OpenStreetMap, 24 catalog products, prices from shoppers and admin-entered flyers.
- Supabase project `smartcart` (ca-central-1): database at migration 0005, magic-link sign-in, owner account is admin.
- Accounts: profile, CASL consent timestamp, export, deletion (price reports de-identified), shopping list synced across devices.
- Prices: submission with validation, outlier review, daily cap and rate limit; admin review queue; receipt photos read on the phone (Tesseract.js) and submitted after review.
- Flyers: admin entry checked against known chains; active flyer prices used in trip plans with a "Flyer price" badge.
- Security: JWT verification (JWKS), RLS on every table, rate limits, body limit (incl. chunked), security headers, CSP on web pages.
- Tests: 81 API tests (SQLite and Postgres), 20 web unit tests, 6 Playwright browser tests (mobile), all in CI.

## Waiting on the owner
1. **Render API key** in `.env` as `RENDER_API_KEY`, then confirm the deploy. Run `venv/bin/python scripts/render_deploy.py --branch feat/beta-completion` for a dry run first.
2. **Revoke the Supabase access token** once the deploy is done (it appeared in a transcript). The deploy script uses it to add the live address to Supabase's sign-in settings, so revoke it after.
3. **Legal:** fill the placeholders in `web/src/legal/*.md` and get a lawyer's review before public launch.
4. **Name and trademark check** for "SmartCart", plus a domain.
5. **Email for magic links:** Supabase's built-in email is limited to a few messages an hour. Before inviting testers, add an SMTP provider (e.g. Resend free tier) in Supabase Auth settings.
6. **Optional:** Sentry DSN (`SMARTCART_SENTRY_DSN`).

## Known gaps / next engineering work
- Price alert emails aren't sent (needs an email provider key).
- French translation (strings are centralised in `web/src/i18n/en.ts`); English-only for the Edmonton beta.
- The gas price is scraped from cheapgasedmonton.ca; check its terms or replace it with a licensed source before public launch.
- The free Render plan sleeps when idle, so the in-process scheduler only runs while the app is awake.
- `main.py` still holds the older endpoints; split them into routers over time.
