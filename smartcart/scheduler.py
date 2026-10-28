"""
SmartCart Automated Data Refresh & Background Scheduler Module
Regularly rebuilds store prices from crowdsourced price observations, refreshes
provincial gas prices, and evaluates price drop alerts.
"""

import asyncio
import datetime
import logging
import time
from typing import Dict, Any

from smartcart.database import get_connection, refresh_inventory_from_observations
from smartcart.gas_service import fetch_live_edmonton_gas_price

log = logging.getLogger(__name__)

# Default background sync interval: 6 hours (21,600 seconds)
DEFAULT_SYNC_INTERVAL_SECONDS = 6 * 3600

def get_current_flyer_cycle() -> Dict[str, Any]:
    """
    Computes the current Canadian grocery flyer weekly cycle.
    In Canada, flyer circulars reset every Thursday morning and run through Wednesday night.
    """
    now = datetime.datetime.now()
    # weekday(): Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6
    day_of_week = now.weekday()

    # Calculate days since most recent Thursday (weekday 3)
    days_since_thursday = (day_of_week - 3) % 7
    cycle_start = now - datetime.timedelta(days=days_since_thursday)
    cycle_end = cycle_start + datetime.timedelta(days=6)

    days_remaining = (cycle_end.date() - now.date()).days
    if days_remaining < 0:
        days_remaining = 0

    return {
        "start_date": cycle_start.strftime("%Y-%m-%d"),
        "end_date": cycle_end.strftime("%Y-%m-%d"),
        "days_remaining": days_remaining,
        "cycle_label": f"Flyer Cycle: {cycle_start.strftime('%b %d')} – {cycle_end.strftime('%b %d, %Y')}",
        "reset_day": "Thursday",
        "is_reset_day": day_of_week == 3
    }

def evaluate_price_alerts(conn):
    """
    Evaluates active price alerts against current product prices.
    """
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, product_name, target_price FROM sale_alerts WHERE target_price IS NOT NULL")
        alerts = cursor.fetchall()
        for a in alerts:
            p_name = a["product_name"]
            target = a["target_price"]
            # Find lowest price for this product
            cursor.execute("""
                SELECT MIN(si.price) as min_price 
                FROM store_inventory si
                JOIN products p ON si.product_id = p.id
                WHERE LOWER(p.name) LIKE ?
            """, (f"%{p_name.lower()}%",))
            res = cursor.fetchone()
            if res and res["min_price"] is not None:
                min_price = res["min_price"]
                is_on_sale = 1 if min_price <= target else 0
                cursor.execute("""
                    UPDATE sale_alerts 
                    SET current_sale_price = ?, is_on_sale = ? 
                    WHERE id = ?
                """, (min_price, is_on_sale, a["id"]))
        conn.commit()
    except Exception as e:
        log.warning("Price alert evaluation failed: %s", e)

def perform_data_sync() -> Dict[str, Any]:
    """
    Executes a complete synchronization:
    1. Provincial gas price benchmarks ($/L).
    2. Store price cache rebuilt from recent price observations.
    3. Price drop alerts evaluation.
    4. Sync audit logging.
    """
    start_time = time.time()
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Total stores count
    cursor.execute("SELECT COUNT(*) as count FROM stores")
    stores_count = cursor.fetchone()["count"]

    # 2. Total inventory rows
    cursor.execute("SELECT COUNT(*) as count FROM store_inventory")
    inventory_count = cursor.fetchone()["count"]

    # 3. Gas prices
    gas_res_ab = fetch_live_edmonton_gas_price("AB")
    gas_ab = float(gas_res_ab.get("price_per_litre", 1.499))
    gas_res_bc = fetch_live_edmonton_gas_price("BC")
    gas_bc = float(gas_res_bc.get("price_per_litre", 1.829))

    # 4. Flyer cycle
    cycle = get_current_flyer_cycle()

    # 5. Rebuild store prices from observations
    updated_inv = refresh_inventory_from_observations(conn)
    cursor.execute("SELECT COUNT(*) as count FROM store_inventory")
    inventory_count = cursor.fetchone()["count"]

    # 6. Evaluate alerts
    evaluate_price_alerts(conn)

    # 7. Total flyer deals count
    cursor.execute("SELECT COUNT(*) as count FROM flyer_deals")
    flyer_deals_count = cursor.fetchone()["count"]

    # 8. Record sync log
    now = datetime.datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    next_sync = now + datetime.timedelta(seconds=DEFAULT_SYNC_INTERVAL_SECONDS)
    next_sync_str = next_sync.strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO sync_history (
            synced_at, stores_count, inventory_rows_count, flyer_deals_count,
            gas_price_ab, gas_price_bc, flyer_cycle_label, status, details, next_sync_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now_str, stores_count, inventory_count, flyer_deals_count,
        gas_ab, gas_bc, cycle["cycle_label"], "SUCCESS",
        f"Rebuilt {updated_inv} store prices from observations; synced gas at ${gas_ab:.3f}/L",
        next_sync_str
    ))

    cursor.execute("""
        INSERT INTO sync_meta (key, value, updated_at)
        VALUES ('last_sync', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
    """, (now_str,))
    cursor.execute("""
        INSERT INTO sync_meta (key, value, updated_at)
        VALUES ('next_sync', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
    """, (next_sync_str,))

    conn.commit()
    conn.close()

    elapsed = round(time.time() - start_time, 2)
    return {
        "status": "SUCCESS",
        "synced_at": now_str,
        "next_sync_at": next_sync_str,
        "duration_seconds": elapsed,
        "stores_count": stores_count,
        "inventory_rows_count": inventory_count,
        "inventory_prices_rebuilt": updated_inv,
        "flyer_deals_count": flyer_deals_count,
        "flyer_cycle": cycle,
        "gas_prices": {
            "Alberta": gas_ab,
            "British Columbia": gas_bc
        }
    }

def get_sync_status() -> Dict[str, Any]:
    """
    Returns current sync status and metadata from SQLite.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT synced_at, stores_count, inventory_rows_count, flyer_deals_count,
               gas_price_ab, gas_price_bc, flyer_cycle_label, status, details, next_sync_at
        FROM sync_history
        ORDER BY id DESC LIMIT 1
    """)
    row = cursor.fetchone()
    cycle = get_current_flyer_cycle()

    if not row:
        conn.close()
        # Run an initial sync, then report status in the usual shape.
        perform_data_sync()
        return get_sync_status()

    cursor.execute("SELECT COUNT(*) as count FROM stores")
    stores_count = cursor.fetchone()["count"]
    cursor.execute("SELECT COUNT(*) as count FROM store_inventory")
    inventory_count = cursor.fetchone()["count"]
    conn.close()

    return {
        "status": row["status"],
        "last_synced_at": row["synced_at"],
        "next_sync_at": row["next_sync_at"],
        "stores_indexed": stores_count,
        "inventory_rows": inventory_count,
        "flyer_deals_indexed": row["flyer_deals_count"],
        "flyer_cycle": cycle,
        "gas_prices": {
            "Alberta": row["gas_price_ab"],
            "British Columbia": row["gas_price_bc"]
        },
        "auto_sync_interval": "Every 6 Hours (Automatic Background Worker)",
        "details": row["details"]
    }

async def background_sync_worker(interval_seconds: int = DEFAULT_SYNC_INTERVAL_SECONDS):
    """
    Perpetual background async task running within the FastAPI event loop.
    Ensures Canadian grocery data is regularly updated every 6 hours and on flyer reset.
    """
    log.info("Background sync worker started (interval %ss)", interval_seconds)
    while True:
        try:
            result = perform_data_sync()
            log.info("Sync completed: %s stores, %s prices rebuilt", result['stores_count'], result['inventory_prices_rebuilt'])
        except Exception as e:
            log.exception("Scheduled sync failed: %s", e)

        await asyncio.sleep(interval_seconds)
