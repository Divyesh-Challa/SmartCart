"""Helpers for authenticated API tests."""

import os
import time
import uuid

import jwt


def make_token(user_id=None, email="shopper@example.com", expires_in=3600, secret=None, audience="authenticated"):
    now = int(time.time())
    claims = {
        "sub": user_id or str(uuid.uuid4()),
        "email": email,
        "aud": audience,
        "role": "authenticated",
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, secret or os.environ["SMARTCART_SUPABASE_JWT_SECRET"], algorithm="HS256")


def auth_headers(user_id=None, **kwargs):
    return {"Authorization": f"Bearer {make_token(user_id, **kwargs)}"}
