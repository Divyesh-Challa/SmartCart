"""The signed-in shopper's list, synced across devices (last write wins)."""

import datetime
import json
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from smartcart.auth import CurrentUser, get_current_user
from smartcart.database import get_connection

router = APIRouter(prefix="/api/me/list", tags=["account"])

MAX_ITEMS = 200


class ListItem(BaseModel):
    id: str = Field(..., max_length=64)
    name: str = Field(..., min_length=1, max_length=120)
    quantity: int = Field(1, ge=1, le=99)


class ShoppingList(BaseModel):
    items: List[ListItem] = Field(default_factory=list, max_length=MAX_ITEMS)


@router.get("")
def get_list(user: CurrentUser = Depends(get_current_user)):
    conn = get_connection()
    try:
        row = conn.execute("SELECT items_json, updated_at FROM shopping_lists WHERE user_id = ?", (user.id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return {"items": [], "updated_at": None}
    return {"items": json.loads(row["items_json"]), "updated_at": row["updated_at"]}


@router.put("")
def save_list(body: ShoppingList, user: CurrentUser = Depends(get_current_user)):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    items_json = json.dumps([item.model_dump() for item in body.items])
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO shopping_lists (user_id, items_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET items_json = excluded.items_json, updated_at = excluded.updated_at
        """, (user.id, items_json, now))
        conn.commit()
    finally:
        conn.close()
    return {"items": json.loads(items_json), "updated_at": now}
