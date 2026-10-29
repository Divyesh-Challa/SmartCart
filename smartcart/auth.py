"""
Authentication: verifies Supabase-issued access tokens (JWTs) and maps them to
a SmartCart user row.

Supabase projects sign tokens either with asymmetric keys published at
{SUPABASE_URL}/auth/v1/.well-known/jwks.json, or (legacy projects) with a shared
HS256 secret. Set SMARTCART_SUPABASE_URL for the former and/or
SMARTCART_SUPABASE_JWT_SECRET for the latter.
"""

import datetime
import ssl
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import certifi
import jwt
from fastapi import Depends, Header, HTTPException, Request

from smartcart.config import get_settings
from smartcart.database import get_connection


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: Optional[str]
    is_admin: bool = False
    trust_score: float = 0.5
    plan: str = "free"

    @property
    def has_full_access(self) -> bool:
        """Every feature, including any future paid ones. Paid-feature checks must use this."""
        return self.is_admin or self.plan != "free"


def auth_configured() -> bool:
    s = get_settings()
    return bool(s.supabase_url or s.supabase_jwt_secret)


@lru_cache
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    # certifi's CA bundle: some Python builds (e.g. python.org on macOS) ship without system CAs.
    return jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=3600,
                           ssl_context=ssl.create_default_context(cafile=certifi.where()))


def decode_access_token(token: str) -> dict:
    """Validate signature, expiry and audience. Raises jwt.InvalidTokenError."""
    s = get_settings()
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "")
    options = {"require": ["exp", "sub"]}

    if alg == "HS256":
        if not s.supabase_jwt_secret:
            raise jwt.InvalidTokenError("HS256 tokens are not accepted by this server")
        return jwt.decode(token, s.supabase_jwt_secret, algorithms=["HS256"],
                          audience=s.supabase_jwt_audience, options=options)

    if not s.supabase_url:
        raise jwt.InvalidTokenError("Asymmetric tokens require SMARTCART_SUPABASE_URL")
    base = s.supabase_url.rstrip("/")
    signing_key = _jwks_client(f"{base}/auth/v1/.well-known/jwks.json").get_signing_key_from_jwt(token)
    return jwt.decode(token, signing_key.key, algorithms=["RS256", "ES256"],
                      audience=s.supabase_jwt_audience, issuer=f"{base}/auth/v1", options=options)


def _upsert_user(user_id: str, email: Optional[str]) -> CurrentUser:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO users (id, email, created_at, last_seen_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET email = COALESCE(excluded.email, users.email),
                                          last_seen_at = excluded.last_seen_at
        """, (user_id, email, now, now))
        if email and email.lower() in {e.lower() for e in get_settings().admin_emails}:
            conn.execute("UPDATE users SET is_admin = 1, plan = 'admin', trust_score = 1.0 WHERE id = ?", (user_id,))
        conn.commit()
        row = conn.execute("SELECT id, email, is_admin, trust_score, plan FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
    return CurrentUser(id=row["id"], email=row["email"], is_admin=bool(row["is_admin"]),
                       trust_score=float(row["trust_score"]), plan=row["plan"])


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def get_optional_user(request: Request, authorization: Optional[str] = Header(None)) -> Optional[CurrentUser]:
    token = _bearer_token(authorization)
    if token is None:
        return None
    if not auth_configured():
        raise HTTPException(status_code=503, detail="Accounts are not available yet.")
    try:
        claims = decode_access_token(token)
    except jwt.PyJWTError as err:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please sign in again.",
                            headers={"WWW-Authenticate": "Bearer"}) from err
    user = _upsert_user(claims["sub"], claims.get("email"))
    request.state.user_id = user.id
    request.state.is_admin = user.is_admin
    return user


def get_current_user(user: Optional[CurrentUser] = Depends(get_optional_user)) -> CurrentUser:
    if user is None:
        if not auth_configured():
            raise HTTPException(status_code=503, detail="Accounts are not available yet.")
        raise HTTPException(status_code=401, detail="Please sign in to continue.",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def require_admin_user(
    user: Optional[CurrentUser] = Depends(get_optional_user),
    x_admin_token: Optional[str] = Header(None),
) -> Optional[CurrentUser]:
    """Admins are users with is_admin = 1, or callers presenting SMARTCART_ADMIN_TOKEN."""
    if user is not None and user.is_admin:
        return user
    expected = get_settings().admin_token
    if expected and x_admin_token == expected:
        return user
    raise HTTPException(status_code=403, detail="Admin access required.")
