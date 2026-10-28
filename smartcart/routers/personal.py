"""Per-user data: shopping trip receipts, savings summary and price alerts."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from smartcart.auth import CurrentUser, get_current_user
from smartcart.database import get_connection

router = APIRouter(prefix="/api", tags=["personal"])


class ReceiptCreateModel(BaseModel):
    store_name: str = Field(..., max_length=120, description="Grocery chain or store name")
    trip_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD format date")
    amount_spent: float = Field(..., ge=0, description="Actual paid amount in CAD")
    regular_amount: float = Field(..., ge=0, description="Regular shelf price amount in CAD")
    category: Optional[str] = Field("Groceries", max_length=60, description="Primary shopping category")
    items_count: Optional[int] = Field(0, ge=0, description="Number of items purchased")
    notes: Optional[str] = Field("", max_length=1000, description="Trip notes or purchased items summary")


class AlertCreateModel(BaseModel):
    product_name: str = Field(..., max_length=120, description="Product to watch for flyer sales")
    category: Optional[str] = Field("Pantry", max_length=60, description="Department/category")
    target_price: Optional[float] = Field(None, gt=0, description="Target notification price in CAD")


@router.get("/savings/summary")
def get_savings_summary(user: CurrentUser = Depends(get_current_user)):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT
            COUNT(*) as trips_count,
            COALESCE(SUM(amount_spent), 0) as total_spent,
            COALESCE(SUM(regular_amount), 0) as total_regular,
            COALESCE(SUM(amount_saved), 0) as total_saved
        FROM receipts WHERE user_id = ?
    """, (user.id,))
    row = c.fetchone()
    trips_count = row["trips_count"]
    total_spent = round(row["total_spent"], 2)
    total_regular = round(row["total_regular"], 2)
    total_saved = round(row["total_saved"], 2)
    savings_percent = round((total_saved / total_regular * 100), 1) if total_regular > 0 else 0.0

    c.execute("""
        SELECT category, SUM(amount_saved) as saved, SUM(amount_spent) as spent
        FROM receipts WHERE user_id = ?
        GROUP BY category
        ORDER BY saved DESC
    """, (user.id,))
    categories = []
    for r in c.fetchall():
        cat_saved = round(r["saved"], 2)
        cat_spent = round(r["spent"], 2)
        categories.append({
            "category": r["category"],
            "saved": cat_saved,
            "spent": cat_spent,
            "share_percent": round(cat_saved / total_saved * 100, 1) if total_saved > 0 else 0
        })
    conn.close()
    return {
        "trips_count": trips_count,
        "total_spent": total_spent,
        "total_regular": total_regular,
        "total_saved": total_saved,
        "savings_percent": savings_percent,
        "avg_savings_per_trip": round(total_saved / trips_count, 2) if trips_count > 0 else 0.0,
        "categories": categories
    }


@router.get("/savings/receipts")
def get_savings_receipts(user: CurrentUser = Depends(get_current_user)):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM receipts WHERE user_id = ? ORDER BY trip_date DESC, id DESC", (user.id,)).fetchall()
    conn.close()
    return {"receipts": [dict(r) for r in rows]}


@router.post("/savings/receipts")
def create_receipt(receipt: ReceiptCreateModel, user: CurrentUser = Depends(get_current_user)):
    spent = round(receipt.amount_spent, 2)
    regular = round(receipt.regular_amount, 2)
    saved = round(max(0.0, regular - spent), 2)
    pct = round((saved / regular * 100)) if regular > 0 else 0

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO receipts (user_id, store_name, trip_date, amount_spent, regular_amount, amount_saved, savings_percent, items_count, category, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user.id, receipt.store_name, receipt.trip_date, spent, regular, saved, pct, receipt.items_count,
          receipt.category or "Groceries", receipt.notes or ""))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return {"status": "ok", "id": new_id, "amount_saved": saved, "savings_percent": pct}


@router.delete("/savings/receipts/{receipt_id}")
def delete_receipt(receipt_id: int, user: CurrentUser = Depends(get_current_user)):
    conn = get_connection()
    c = conn.execute("DELETE FROM receipts WHERE id = ? AND user_id = ?", (receipt_id, user.id))
    conn.commit()
    deleted = c.rowcount
    conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    return {"status": "ok", "deleted": True}


@router.get("/alerts")
def get_alerts(user: CurrentUser = Depends(get_current_user)):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM sale_alerts WHERE user_id = ? ORDER BY is_on_sale DESC, id DESC", (user.id,)).fetchall()
    conn.close()
    return {"alerts": [dict(r) for r in rows]}


@router.post("/alerts")
def create_alert(alert: AlertCreateModel, user: CurrentUser = Depends(get_current_user)):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT d.sale_price, d.original_price, f.banner
        FROM flyer_deals d
        JOIN flyers f ON f.id = d.flyer_id
        WHERE LOWER(d.title) LIKE ?
        ORDER BY d.sale_price ASC LIMIT 1
    """, (f"%{alert.product_name.lower().strip()}%",))
    deal_row = c.fetchone()

    is_on_sale = 1 if deal_row else 0
    curr_price = deal_row["sale_price"] if deal_row else None
    reg_price = deal_row["original_price"] if deal_row else None
    banner = deal_row["banner"] if deal_row else None

    c.execute("""
        INSERT INTO sale_alerts (user_id, product_name, category, target_price, current_sale_price, regular_price, banner, is_on_sale)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user.id, alert.product_name, alert.category or "Pantry", alert.target_price, curr_price, reg_price, banner, is_on_sale))
    conn.commit()
    alert_id = c.lastrowid
    conn.close()
    return {"status": "ok", "id": alert_id, "is_on_sale": bool(is_on_sale)}


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int, user: CurrentUser = Depends(get_current_user)):
    conn = get_connection()
    c = conn.execute("DELETE FROM sale_alerts WHERE id = ? AND user_id = ?", (alert_id, user.id))
    conn.commit()
    deleted = c.rowcount
    conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return {"status": "ok", "deleted": True}
