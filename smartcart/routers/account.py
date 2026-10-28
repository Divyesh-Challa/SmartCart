"""
Account endpoints: profile, marketing consent, data export and deletion
(PIPEDA / Québec Law 25 access and erasure requests).
"""

import datetime
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from smartcart.auth import CurrentUser, get_current_user
from smartcart.config import get_settings
from smartcart.database import get_connection, refresh_inventory_from_observations

router = APIRouter(prefix="/api/me", tags=["account"])
log = logging.getLogger(__name__)

OWNED_TABLES = ("receipts", "sale_alerts", "recipe_requests")


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=80)
    home_postal_code: Optional[str] = Field(None, max_length=7)
    # CASL: consent to commercial email must be express and is recorded with a timestamp.
    marketing_opt_in: Optional[bool] = None


def _profile(conn, user_id: str) -> dict:
    row = conn.execute("""
        SELECT id, email, display_name, plan, home_postal_code, marketing_opt_in,
               marketing_opt_in_at, created_at, is_admin
        FROM users WHERE id = ?
    """, (user_id,)).fetchone()
    data = dict(row)
    data["marketing_opt_in"] = bool(data["marketing_opt_in"])
    data["is_admin"] = bool(data["is_admin"])
    return data


@router.get("")
def get_me(user: CurrentUser = Depends(get_current_user)):
    conn = get_connection()
    try:
        profile = _profile(conn, user.id)
        profile["price_reports"] = conn.execute(
            "SELECT COUNT(*) AS n FROM price_observations WHERE submitted_by = ?", (user.id,)
        ).fetchone()["n"]
    finally:
        conn.close()
    return profile


@router.patch("")
def update_me(body: ProfileUpdate, user: CurrentUser = Depends(get_current_user)):
    conn = get_connection()
    try:
        if body.display_name is not None:
            conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (body.display_name.strip() or None, user.id))
        if body.home_postal_code is not None:
            pc = body.home_postal_code.replace(" ", "").upper()
            conn.execute("UPDATE users SET home_postal_code = ? WHERE id = ?", (pc or None, user.id))
        if body.marketing_opt_in is not None:
            stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            conn.execute("UPDATE users SET marketing_opt_in = ?, marketing_opt_in_at = ? WHERE id = ?",
                         (1 if body.marketing_opt_in else 0, stamp, user.id))
        conn.commit()
        return _profile(conn, user.id)
    finally:
        conn.close()


@router.get("/export")
def export_my_data(user: CurrentUser = Depends(get_current_user)):
    """Everything SmartCart stores about the signed-in user, as JSON."""
    conn = get_connection()
    try:
        data = {"profile": _profile(conn, user.id)}
        for table in OWNED_TABLES:
            data[table] = [dict(r) for r in conn.execute(f"SELECT * FROM {table} WHERE user_id = ?", (user.id,)).fetchall()]
        data["price_observations"] = [dict(r) for r in conn.execute(
            "SELECT * FROM price_observations WHERE submitted_by = ?", (user.id,)
        ).fetchall()]
    finally:
        conn.close()
    data["exported_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    return data


def _delete_supabase_auth_user(user_id: str) -> bool:
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_role_key):
        return False
    resp = httpx.delete(
        f"{s.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
        headers={"apikey": s.supabase_service_role_key, "Authorization": f"Bearer {s.supabase_service_role_key}"},
        timeout=10,
    )
    if resp.status_code not in (200, 204, 404):
        log.error("Supabase auth user deletion failed for %s: %s", user_id, resp.status_code)
        raise HTTPException(status_code=502, detail="Couldn't finish deleting your sign-in. Please try again.")
    return True


@router.delete("")
def delete_me(user: CurrentUser = Depends(get_current_user)):
    """
    Deletes the account and all personal data. Price reports are kept but
    de-identified (submitter and photo removed), so shared store prices stay
    accurate for other shoppers.
    """
    conn = get_connection()
    try:
        for table in OWNED_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user.id,))
        conn.execute("UPDATE price_observations SET submitted_by = NULL, photo_key = NULL WHERE submitted_by = ?", (user.id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user.id,))
        conn.commit()
        refresh_inventory_from_observations(conn)
    finally:
        conn.close()
    auth_deleted = _delete_supabase_auth_user(user.id)
    return {"deleted": True, "sign_in_removed": auth_deleted}
