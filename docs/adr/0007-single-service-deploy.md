# 0007: Serve the web app from the API as one Render service

**Status:** Accepted (2026-10-28). Supersedes the hosting part of 0006.

## Context
ADR 0006 planned to host the PWA separately (e.g. Cloudflare Pages) and call the API across origins. For the free-tier beta that means two deploys, build-time environment variables baked into the bundle, and CORS to keep in sync with every address change. The owner already uses Render, and Render's free web service can run the Docker image.

## Decision
The Docker image builds `web/` in a Node stage and the FastAPI app serves `web/dist` with an SPA fallback (fingerprinted assets cached for a year, everything else revalidated). The web app reads its Supabase URL and public key from `/config.js` at runtime, so one build works in every environment. `render.yaml` defines a single free web service in Virginia (closest Render region to the Montreal database); the scheduler runs in-process because the free plan has no workers. `scripts/render_deploy.py` creates or updates the service through Render's API.

## Consequences
- One address, one deploy, no CORS for the app itself; the legacy HTML pages are gone.
- A strict Content-Security-Policy is possible because everything comes from one origin (plus the OCR CDN, Supabase and Open Food Facts images).
- The free service sleeps after 15 minutes idle: the first visit afterwards is slow, and the in-process scheduler doesn't run while asleep. Prices come from shoppers and flyers, so nothing goes stale beyond the gas price. Moving to a paid instance or a separate worker later needs no code changes.
- Static files are served by Python rather than a CDN. That's fine at beta traffic; a CDN can be put in front later.
