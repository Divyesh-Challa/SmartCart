# 0005: Supabase Auth with server-side JWT verification

**Status:** Accepted (2026-10-28)

## Decision
The PWA signs users in with Supabase (email magic links). The API verifies the access token itself, via JWKS (`/auth/v1/.well-known/jwks.json`) or the legacy HS256 secret, checking audience, issuer and expiry. On first sight it creates a `users` row keyed by the token's `sub`. Personal tables carry `user_id`, and every query filters by it.

## Consequences
- The API never handles passwords.
- Account deletion removes personal rows, de-identifies price reports, and (if the service-role key is set) deletes the Supabase auth user.
- Admins are users with `is_admin = 1`, or callers presenting `SMARTCART_ADMIN_TOKEN`.
