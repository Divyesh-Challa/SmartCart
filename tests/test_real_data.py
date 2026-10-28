"""
Tests for the real-data pipeline: OpenStreetMap store loading, crowdsourced
price observations, the store_inventory price cache, unsourced-data purge,
database-backed flyers, and the interim admin guard on flyer uploads.
"""

import base64
import datetime
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("SMARTCART_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="smartcart-test-"), "test.db"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

import smartcart.database as database
from smartcart import flyers_service
from smartcart.main import app


class RealDataTestCase(unittest.TestCase):
    """Each test gets its own empty database file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="smartcart-real-")
        self._patch = mock.patch.object(database, "DB_PATH", Path(self._tmp.name) / "real.db")
        self._patch.start()
        database.init_db()
        self.conn = database.get_connection()
        database.seed_product_catalog(self.conn)

    def tearDown(self):
        self.conn.close()
        self._patch.stop()
        self._tmp.cleanup()

    def product_id(self, name):
        return self.conn.execute("SELECT id FROM products WHERE name = ?", (name,)).fetchone()["id"]

    def first_store_id(self):
        return self.conn.execute("SELECT id FROM stores ORDER BY id LIMIT 1").fetchone()["id"]


class TestStoreData(RealDataTestCase):
    def test_edmonton_export_is_well_formed(self):
        payload = json.loads((database.DATA_DIR / "edmonton_stores.json").read_text())
        self.assertEqual(payload["license"], "ODbL 1.0")
        self.assertIn("OpenStreetMap", payload["attribution"])
        self.assertGreater(len(payload["stores"]), 100)
        osm_ids = [s["osm_id"] for s in payload["stores"]]
        self.assertEqual(len(osm_ids), len(set(osm_ids)))
        for st in payload["stores"]:
            self.assertTrue(53.2 < st["latitude"] < 53.8, st)
            self.assertTrue(-114.0 < st["longitude"] < -113.1, st)
            self.assertTrue(st["name"] and st["banner"] and st["city"], st)

    def test_load_real_stores_is_idempotent(self):
        first = database.load_real_stores(self.conn, "edmonton")
        second = database.load_real_stores(self.conn, "edmonton")
        self.assertEqual(first, second)
        count = self.conn.execute("SELECT COUNT(*) AS c FROM stores").fetchone()["c"]
        self.assertEqual(count, first)
        unsourced = self.conn.execute(
            "SELECT COUNT(*) AS c FROM stores WHERE osm_id IS NULL OR source != 'openstreetmap'"
        ).fetchone()["c"]
        self.assertEqual(unsourced, 0)

    def test_costco_requires_membership(self):
        database.load_real_stores(self.conn, "edmonton")
        rows = self.conn.execute("SELECT requires_membership FROM stores WHERE banner = 'Costco'").fetchall()
        self.assertTrue(rows)
        self.assertTrue(all(r["requires_membership"] == 1 for r in rows))


class TestPriceObservations(RealDataTestCase):
    def setUp(self):
        super().setUp()
        database.load_real_stores(self.conn, "edmonton")
        self.store_id = self.first_store_id()
        self.butter = self.product_id("Salted Butter")

    def test_no_observations_means_no_prices(self):
        self.assertEqual(database.refresh_inventory_from_observations(self.conn), 0)
        count = self.conn.execute("SELECT COUNT(*) AS c FROM store_inventory").fetchone()["c"]
        self.assertEqual(count, 0)

    def test_cache_uses_median_and_records_provenance(self):
        for price in (5.49, 5.99, 7.99):
            database.record_price_observation(self.conn, self.store_id, price, "receipt", product_id=self.butter)
        self.assertEqual(database.refresh_inventory_from_observations(self.conn), 1)
        row = self.conn.execute(
            "SELECT * FROM store_inventory WHERE store_id = ? AND product_id = ?", (self.store_id, self.butter)
        ).fetchone()
        self.assertAlmostEqual(row["price"], 5.99)
        self.assertEqual(row["observation_count"], 3)
        self.assertEqual(row["source"], "receipt")
        self.assertIsNotNone(row["last_observed_at"])

    def test_stale_and_rejected_observations_are_ignored(self):
        old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=45)).isoformat()
        database.record_price_observation(self.conn, self.store_id, 4.99, "manual", product_id=self.butter, observed_at=old)
        rejected = database.record_price_observation(self.conn, self.store_id, 0.99, "manual", product_id=self.butter)
        self.conn.execute("UPDATE price_observations SET status = 'rejected' WHERE id = ?", (rejected,))
        self.conn.commit()
        self.assertEqual(database.refresh_inventory_from_observations(self.conn), 0)

    def test_invalid_observations_are_refused(self):
        with self.assertRaises(ValueError):
            database.record_price_observation(self.conn, self.store_id, 4.99, "guess", product_id=self.butter)
        with self.assertRaises(ValueError):
            database.record_price_observation(self.conn, self.store_id, 0, "receipt", product_id=self.butter)
        with self.assertRaises(ValueError):
            database.record_price_observation(self.conn, self.store_id, 4.99, "receipt")


class TestPriceImportScript(RealDataTestCase):
    def test_import_validates_rows_and_rebuilds_cache(self):
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import import_prices

        database.load_real_stores(self.conn, "edmonton")
        osm_id = self.conn.execute("SELECT osm_id FROM stores ORDER BY id LIMIT 1").fetchone()["osm_id"]
        today = datetime.date.today().isoformat()
        rows = [
            {"store_osm_id": osm_id, "item": "salted butter", "price": "5.99", "observed_at": today, "source": "receipt"},
            {"store_osm_id": osm_id, "item": "dozen eggs", "price": "4.29", "observed_at": today},
            {"store_osm_id": "node/0", "item": "butter", "price": "5.99", "observed_at": today},
            {"store_osm_id": osm_id, "item": "butter", "price": "abc", "observed_at": today},
            {"store_osm_id": osm_id, "item": "butter", "price": "5.99", "observed_at": today, "source": "guess"},
            {"store_osm_id": osm_id, "item": "xyzzy widget", "price": "1.00", "observed_at": today},
        ]
        imported, rebuilt, problems = import_prices.import_rows(rows, submitted_by="tester")
        self.assertEqual(imported, 2)
        self.assertEqual(rebuilt, 2)
        self.assertEqual(len(problems), 4)


class TestPurgeUnsourcedData(RealDataTestCase):
    def test_purge_removes_generated_rows_and_keeps_osm_stores(self):
        database.load_real_stores(self.conn, "edmonton")
        real_count = self.conn.execute("SELECT COUNT(*) AS c FROM stores").fetchone()["c"]
        cur = self.conn.cursor()
        cur.execute("""INSERT INTO stores (name, banner, address, latitude, longitude)
                       VALUES ('No Frills - Edmonton NW', 'No Frills', '123 Fake St', 53.5, -113.5)""")
        fake_store = cur.lastrowid
        cur.execute("""INSERT INTO store_inventory (store_id, product_id, price, unit_price)
                       VALUES (?, ?, 4.99, 1.0)""", (fake_store, self.product_id("Salted Butter")))
        cur.execute("""INSERT INTO flyers (banner, title, valid_from, valid_to)
                       VALUES ('Walmart', 'Demo', '2026-10-01', '2026-10-07')""")
        self.conn.commit()

        removed = database.purge_unsourced_data(self.conn)
        self.assertEqual(removed["stores"], 1)
        self.assertEqual(removed["store_inventory"], 1)
        self.assertEqual(removed["flyers"], 1)
        remaining = self.conn.execute("SELECT COUNT(*) AS c FROM stores").fetchone()["c"]
        self.assertEqual(remaining, real_count)


class TestDatabaseFlyers(RealDataTestCase):
    def test_only_currently_valid_flyers_are_returned(self):
        today = datetime.date.today()
        cur = self.conn.cursor()
        cur.execute("INSERT INTO flyers (banner, title, valid_from, valid_to) VALUES ('No Frills', 'Current', ?, ?)",
                    ((today - datetime.timedelta(days=1)).isoformat(), (today + datetime.timedelta(days=5)).isoformat()))
        current_id = cur.lastrowid
        cur.execute("INSERT INTO flyers (banner, title, valid_from, valid_to) VALUES ('Walmart', 'Expired', '2020-01-01', '2020-01-07')")
        cur.execute("""INSERT INTO flyer_deals (flyer_id, title, category, sale_price, original_price)
                       VALUES (?, 'Salted Butter 454g', 'Dairy', 4.99, 6.99)""", (current_id,))
        self.conn.commit()

        flyers = flyers_service.fetch_live_flyers()
        self.assertEqual([f["title"] for f in flyers], ["Current"])
        self.assertEqual(flyers[0]["deals_count"], 1)
        self.assertEqual(flyers_service.fetch_flyer_deals(current_id)[0]["price"], 4.99)
        hits = flyers_service.search_flyer_items("butter")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["merchant"], "No Frills")

    def test_no_flyers_on_file_returns_empty(self):
        self.assertEqual(flyers_service.fetch_live_flyers(), [])
        self.assertEqual(flyers_service.search_flyer_items("eggs"), [])


class TestFlyerUploadGuard(RealDataTestCase):
    PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()

    def setUp(self):
        super().setUp()
        self.client = TestClient(app)
        self.upload_dir = Path(database.__file__).parent / "static" / "uploads" / "flyers"

    def tearDown(self):
        for f in self.upload_dir.glob("test_banner_p*"):
            f.unlink()
        super().tearDown()

    def test_upload_requires_admin_token(self):
        body = {"banner": "Test Banner", "page_number": 1, "image_base64": self.PNG}
        with mock.patch.dict(os.environ, {"SMARTCART_ADMIN_TOKEN": "s3cret"}):
            self.assertEqual(self.client.post("/api/flyers/upload", json=body).status_code, 403)
            bad = self.client.post("/api/flyers/upload", json=body, headers={"X-Admin-Token": "nope"})
            self.assertEqual(bad.status_code, 403)
            ok = self.client.post("/api/flyers/upload", json=body, headers={"X-Admin-Token": "s3cret"})
            self.assertEqual(ok.status_code, 200, ok.text)
            self.assertTrue(ok.json()["image_url"].endswith(".png"))

    def test_upload_disabled_when_no_token_configured(self):
        body = {"banner": "Test Banner", "page_number": 1, "image_base64": self.PNG}
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SMARTCART_ADMIN_TOKEN", None)
            res = self.client.post("/api/flyers/upload", json=body, headers={"X-Admin-Token": ""})
            self.assertEqual(res.status_code, 403)

    def test_upload_rejects_non_images(self):
        body = {"banner": "Test Banner", "page_number": 1,
                "image_base64": base64.b64encode(b"<script>alert(1)</script>").decode()}
        with mock.patch.dict(os.environ, {"SMARTCART_ADMIN_TOKEN": "s3cret"}):
            res = self.client.post("/api/flyers/upload", json=body, headers={"X-Admin-Token": "s3cret"})
            self.assertEqual(res.status_code, 415)


if __name__ == "__main__":
    unittest.main()
