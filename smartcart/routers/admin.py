"""
Admin endpoints: flyer entry (until a licensed flyer feed is connected),
flyer page images, and moderation of price reports held for review.
"""

import base64
import datetime
import re
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from smartcart.auth import CurrentUser, require_admin_user
from smartcart.database import extract_unit_size, get_connection, refresh_inventory_from_observations
from smartcart.normalizer import match_product_in_catalog

router = APIRouter(tags=["admin"])

MAX_FLYER_IMAGE_BYTES = 5 * 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "flyers"

TRUST_REWARD = 0.02
TRUST_PENALTY = 0.1


class FlyerDealIn(BaseModel):
    title: str = Field(..., max_length=200)
    category: str = Field(..., max_length=60)
    sale_price: float = Field(..., gt=0, le=1000)
    original_price: Optional[float] = Field(None, gt=0, le=1000)
    product_id: Optional[int] = None
    page_number: int = Field(1, ge=1, le=50)
    unit_size: Optional[str] = Field(None, max_length=40)
    discount_text: Optional[str] = Field(None, max_length=80)
    is_front_page: bool = False


class FlyerIn(BaseModel):
    banner: str = Field(..., max_length=80)
    title: str = Field(..., max_length=160)
    valid_from: datetime.date
    valid_to: datetime.date
    total_pages: int = Field(1, ge=1, le=50)
    badge_text: Optional[str] = Field(None, max_length=60)
    deals: List[FlyerDealIn] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def check_dates(self):
        if self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from")
        return self


class UploadFlyerRequest(BaseModel):
    banner: str = Field(..., max_length=80, description="Supermarket chain (e.g. No Frills, Walmart, Superstore)")
    page_number: int = Field(1, description="Page number")
    image_base64: str = Field(..., description="Base64 or Data URL of the flyer page image")
    title: Optional[str] = Field(None, max_length=160, description="Optional title for the flyer page")


class ModerationDecision(BaseModel):
    status: Literal["accepted", "rejected"]


def _catalog_product_id(title: str) -> Optional[int]:
    """Link a flyer line to the catalog product it advertises, so trip plans can use the sale price."""
    match = match_product_in_catalog(title)
    return match["id"] if match else None


def _store_banners(conn) -> dict:
    rows = conn.execute("SELECT DISTINCT banner FROM stores WHERE banner IS NOT NULL ORDER BY banner").fetchall()
    return {r["banner"].strip().lower(): r["banner"] for r in rows}


@router.get("/api/admin/banners")
def list_banners(admin: Optional[CurrentUser] = Depends(require_admin_user)):
    """Store chains we have locations for; a flyer's banner must be one of these."""
    conn = get_connection()
    try:
        return {"banners": list(_store_banners(conn).values())}
    finally:
        conn.close()


@router.post("/api/admin/flyers", status_code=201)
def create_flyer(body: FlyerIn, admin: Optional[CurrentUser] = Depends(require_admin_user)):
    conn = get_connection()
    try:
        banner = _store_banners(conn).get(body.banner.strip().lower())
        if banner is None:
            raise HTTPException(status_code=422, detail=f"No stores found for the chain '{body.banner}'. Pick one from the list.")
        body.banner = banner
        c = conn.cursor()
        c.execute("""
            INSERT INTO flyers (banner, title, total_pages, valid_from, valid_to, badge_text)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (body.banner, body.title, body.total_pages, body.valid_from.isoformat(), body.valid_to.isoformat(), body.badge_text))
        flyer_id = c.lastrowid
        c.executemany("""
            INSERT INTO flyer_deals (
                flyer_id, product_id, title, item_name, category, page_number, original_price, sale_price,
                discount_text, is_front_page, store_name, unit_size, valid_until
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (flyer_id, d.product_id or _catalog_product_id(d.title), d.title, d.title, d.category, d.page_number, d.original_price, d.sale_price,
             d.discount_text, 1 if d.is_front_page else 0, body.banner, d.unit_size or extract_unit_size(d.title),
             body.valid_to.isoformat())
            for d in body.deals
        ])
        conn.commit()
    finally:
        conn.close()
    return {"id": flyer_id, "deals": len(body.deals)}


@router.delete("/api/admin/flyers/{flyer_id}")
def delete_flyer(flyer_id: int, admin: Optional[CurrentUser] = Depends(require_admin_user)):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM flyer_deals WHERE flyer_id = ?", (flyer_id,))
        deleted = conn.execute("DELETE FROM flyers WHERE id = ?", (flyer_id,)).rowcount
        conn.commit()
    finally:
        conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Flyer not found.")
    return {"deleted": True}


@router.get("/api/admin/observations")
def list_observations(
    status: Literal["pending", "accepted", "rejected"] = "pending",
    limit: int = Query(100, ge=1, le=500),
    admin: Optional[CurrentUser] = Depends(require_admin_user),
):
    conn = get_connection()
    rows = conn.execute("""
        SELECT o.*, s.name AS store_name, p.name AS product_name,
               si.price AS current_median, si.observation_count AS current_count
        FROM price_observations o
        JOIN stores s ON s.id = o.store_id
        LEFT JOIN products p ON p.id = o.product_id
        LEFT JOIN store_inventory si ON si.store_id = o.store_id AND si.product_id = o.product_id
        WHERE o.status = ?
        ORDER BY o.id DESC LIMIT ?
    """, (status, limit)).fetchall()
    conn.close()
    return {"observations": [dict(r) for r in rows]}


@router.post("/api/admin/observations/{observation_id}")
def moderate_observation(observation_id: int, body: ModerationDecision,
                         admin: Optional[CurrentUser] = Depends(require_admin_user)):
    conn = get_connection()
    try:
        row = conn.execute("SELECT store_id, product_id, submitted_by FROM price_observations WHERE id = ?",
                           (observation_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Price report not found.")
        conn.execute("UPDATE price_observations SET status = ? WHERE id = ?", (body.status, observation_id))
        submitter = conn.execute("SELECT trust_score FROM users WHERE id = ?", (row["submitted_by"],)).fetchone() \
            if row["submitted_by"] else None
        if submitter:
            delta = TRUST_REWARD if body.status == "accepted" else -TRUST_PENALTY
            new_score = round(min(1.0, max(0.0, submitter["trust_score"] + delta)), 3)
            conn.execute("UPDATE users SET trust_score = ? WHERE id = ?", (new_score, row["submitted_by"]))
        conn.commit()
        if row["product_id"] is not None:
            refresh_inventory_from_observations(conn, store_id=row["store_id"], product_id=row["product_id"])
    finally:
        conn.close()
    return {"id": observation_id, "status": body.status}


@router.post("/api/flyers/upload")
def upload_custom_flyer_page(req: UploadFlyerRequest, admin: Optional[CurrentUser] = Depends(require_admin_user)):
    if not 1 <= req.page_number <= 50:
        raise HTTPException(status_code=400, detail="page_number must be between 1 and 50.")

    raw_b64 = req.image_base64
    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]
    if len(raw_b64) > MAX_FLYER_IMAGE_BYTES * 4 // 3 + 4:
        raise HTTPException(status_code=413, detail="Image exceeds 5 MB limit.")

    try:
        img_bytes = base64.b64decode(raw_b64, validate=True)
    except ValueError as err:
        raise HTTPException(status_code=400, detail="Image is not valid base64.") from err
    if img_bytes.startswith(PNG_MAGIC):
        ext = "png"
    elif img_bytes.startswith(JPEG_MAGIC):
        ext = "jpg"
    else:
        raise HTTPException(status_code=415, detail="Only PNG and JPEG images are accepted.")

    banner_clean = re.sub(r'[^a-zA-Z0-9]', '_', req.banner).lower()
    filename = f"{banner_clean}_p{req.page_number}.{ext}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / filename).write_bytes(img_bytes)
    image_url = f"/static/uploads/flyers/{filename}"

    conn = get_connection()
    conn.execute("""
        INSERT INTO custom_flyer_pages (banner, page_number, image_url, title)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(banner, page_number) DO UPDATE SET
            image_url = excluded.image_url,
            title = excluded.title,
            created_at = CURRENT_TIMESTAMP
    """, (req.banner, req.page_number, image_url, req.title or f"{req.banner} Page {req.page_number}"))
    conn.commit()
    conn.close()

    return {"status": "ok", "banner": req.banner, "page_number": req.page_number, "image_url": image_url}


@router.delete("/api/flyers/custom-page")
def delete_custom_flyer_page(banner: str = Query(...), page_number: int = Query(...),
                             admin: Optional[CurrentUser] = Depends(require_admin_user)):
    conn = get_connection()
    conn.execute("DELETE FROM custom_flyer_pages WHERE LOWER(banner) = LOWER(?) AND page_number = ?", (banner, page_number))
    conn.commit()
    conn.close()
    return {"status": "ok", "deleted": True}
