"""
Crowdsourced prices: shoppers submit what they paid, and everyone sees the
recent median per store with how fresh it is and how many reports back it.
"""

import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from smartcart.auth import CurrentUser, get_current_user
from smartcart.barcodes import normalize_barcode
from smartcart.config import get_settings
from smartcart.database import (
    PRICE_OBSERVATION_WINDOW_DAYS,
    get_connection,
    record_price_observation,
    refresh_inventory_from_observations,
)
from smartcart.normalizer import match_product_in_catalog
from smartcart.security import limiter

router = APIRouter(prefix="/api", tags=["prices"])

MAX_DAILY_SUBMISSIONS = 200
MIN_PRICE, MAX_PRICE = 0.05, 1000.0
# A report this far from the current median is held for review instead of
# changing what everyone sees.
PLAUSIBLE_RATIO = 3.0
# Accounts below this trust level have every report reviewed.
REVIEW_TRUST_THRESHOLD = 0.2


class PriceSubmission(BaseModel):
    store_id: int
    price: float = Field(..., gt=0, description="Shelf price paid, in CAD")
    item_name: Optional[str] = Field(None, max_length=200, description="Item as written on the receipt or shelf tag")
    product_id: Optional[int] = None
    upc: Optional[str] = Field(None, max_length=20)
    observed_on: datetime.date = Field(..., description="Date the price was seen (YYYY-MM-DD)")
    is_sale: bool = False
    source: Literal["receipt", "manual"] = "manual"


def _review_status(conn, user: CurrentUser, store_id: int, product_id: Optional[int], price: float) -> str:
    if user.trust_score < REVIEW_TRUST_THRESHOLD:
        return "pending"
    if product_id is None:
        return "accepted"
    row = conn.execute(
        "SELECT price, observation_count FROM store_inventory WHERE store_id = ? AND product_id = ?",
        (store_id, product_id),
    ).fetchone()
    if row and row["observation_count"] >= 2:
        ratio = price / row["price"]
        if ratio > PLAUSIBLE_RATIO or ratio < 1 / PLAUSIBLE_RATIO:
            return "pending"
    return "accepted"


@router.post("/prices/observations", status_code=201)
@limiter.limit(lambda: get_settings().rate_limit_price_submissions)
def submit_price(request: Request, body: PriceSubmission, user: CurrentUser = Depends(get_current_user)):
    if not MIN_PRICE <= body.price <= MAX_PRICE:
        raise HTTPException(status_code=422, detail=f"Price must be between ${MIN_PRICE:.2f} and ${MAX_PRICE:.0f}.")
    today = datetime.date.today()
    if body.observed_on > today + datetime.timedelta(days=1):
        raise HTTPException(status_code=422, detail="observed_on can't be in the future.")
    if body.observed_on < today - datetime.timedelta(days=PRICE_OBSERVATION_WINDOW_DAYS):
        raise HTTPException(status_code=422, detail=f"Only prices from the last {PRICE_OBSERVATION_WINDOW_DAYS} days are accepted.")

    upc = normalize_barcode(body.upc) if body.upc else None
    conn = get_connection()
    try:
        if not conn.execute("SELECT 1 FROM stores WHERE id = ?", (body.store_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Store not found.")

        product_id = body.product_id
        if product_id is not None:
            if not conn.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone():
                raise HTTPException(status_code=404, detail="Product not found.")
        elif body.item_name:
            match = match_product_in_catalog(body.item_name)
            product_id = match["id"] if match else None
        if product_id is None and not upc:
            raise HTTPException(status_code=422, detail="Tell us which item this is: pick a product, scan the barcode, or describe it.")

        since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).isoformat(timespec="seconds")
        recent = conn.execute(
            "SELECT COUNT(*) AS n FROM price_observations WHERE submitted_by = ? AND created_at >= ?",
            (user.id, since),
        ).fetchone()["n"]
        if recent >= MAX_DAILY_SUBMISSIONS:
            raise HTTPException(status_code=429, detail="Daily price submission limit reached. Thanks for helping!")

        status = _review_status(conn, user, body.store_id, product_id, body.price)
        obs_id = record_price_observation(
            conn,
            store_id=body.store_id,
            price=body.price,
            source=body.source,
            observed_at=datetime.datetime.combine(body.observed_on, datetime.time(12), datetime.timezone.utc).isoformat(timespec="seconds"),
            product_id=product_id,
            upc=upc,
            raw_item_name=body.item_name,
            is_sale=body.is_sale,
            submitted_by=user.id,
            trust_score=user.trust_score,
        )
        conn.execute("UPDATE price_observations SET status = ?, created_at = ? WHERE id = ?",
                     (status, datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), obs_id))
        conn.commit()
        if status == "accepted" and product_id is not None:
            refresh_inventory_from_observations(conn, store_id=body.store_id, product_id=product_id)
    finally:
        conn.close()

    return {"id": obs_id, "status": status, "product_id": product_id, "upc": upc}


@router.get("/prices/observations/mine")
def my_observations(user: CurrentUser = Depends(get_current_user), limit: int = Query(50, ge=1, le=200)):
    conn = get_connection()
    rows = conn.execute("""
        SELECT o.id, o.store_id, s.name AS store_name, o.product_id, p.name AS product_name, o.upc,
               o.raw_item_name, o.price, o.is_sale, o.source, o.observed_at, o.status
        FROM price_observations o
        JOIN stores s ON s.id = o.store_id
        LEFT JOIN products p ON p.id = o.product_id
        WHERE o.submitted_by = ?
        ORDER BY o.id DESC LIMIT ?
    """, (user.id, limit)).fetchall()
    conn.close()
    return {"observations": [dict(r) for r in rows]}


@router.delete("/prices/observations/{observation_id}")
def delete_my_observation(observation_id: int, user: CurrentUser = Depends(get_current_user)):
    conn = get_connection()
    try:
        row = conn.execute("SELECT store_id, product_id FROM price_observations WHERE id = ? AND submitted_by = ?",
                           (observation_id, user.id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Price report not found.")
        conn.execute("DELETE FROM price_observations WHERE id = ?", (observation_id,))
        conn.commit()
        if row["product_id"] is not None:
            refresh_inventory_from_observations(conn, store_id=row["store_id"], product_id=row["product_id"])
    finally:
        conn.close()
    return {"deleted": True}


@router.get("/stores/{store_id}/prices")
def store_prices(store_id: int):
    """Current prices on file for one store, with freshness and report counts."""
    conn = get_connection()
    store = conn.execute("SELECT id, name, banner, address, city, latitude, longitude FROM stores WHERE id = ?",
                         (store_id,)).fetchone()
    if not store:
        conn.close()
        raise HTTPException(status_code=404, detail="Store not found.")
    rows = conn.execute("""
        SELECT si.product_id, p.name AS product_name, p.category, si.price, si.unit_price,
               si.observation_count, si.last_observed_at, si.source
        FROM store_inventory si JOIN products p ON p.id = si.product_id
        WHERE si.store_id = ?
        ORDER BY p.category, p.name
    """, (store_id,)).fetchall()
    conn.close()
    return {"store": dict(store), "prices": [dict(r) for r in rows], "window_days": PRICE_OBSERVATION_WINDOW_DAYS}


@router.get("/products")
def list_products(q: Optional[str] = Query(None, max_length=100)):
    """The product catalog shoppers can report prices against."""
    conn = get_connection()
    sql = "SELECT id, name, category, brand, package_quantity, package_unit FROM products"
    params: tuple = ()
    if q:
        sql += " WHERE LOWER(name) LIKE ? OR LOWER(aliases) LIKE ?"
        params = (f"%{q.lower()}%", f"%{q.lower()}%")
    rows = conn.execute(sql + " ORDER BY category, name", params).fetchall()
    conn.close()
    return {"products": [dict(r) for r in rows]}
