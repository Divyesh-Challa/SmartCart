# 0006: React + Vite PWA as a separate frontend

**Status:** Accepted (2026-10-28)

## Context
The prototype UI was seven large HTML pages using the Tailwind CDN and heavy WebGL effects, built for desktop.

## Decision
A mobile-first React + TypeScript app in `web/`, built with Vite and compiled Tailwind, installable as a PWA. It's hosted separately (e.g. Cloudflare Pages) and calls the API through `VITE_API_URL`, with CORS restricted to its origin. The service worker never caches `/api` responses, so prices are always current. All strings sit in `src/i18n/en.ts`, ready for French.

## Consequences
- The legacy HTML pages remain served by FastAPI until the PWA is live, then they can be removed.
- Without Supabase settings the app still works for browsing; accounts show as unavailable.
