"""
Tests for accounts (token verification, profile, export, deletion), shopper
price submissions and moderation, admin flyer entry, and HTTP hardening.
"""

import datetime
import unittest

from fastapi.testclient import TestClient

from smartcart.config import local_today
from smartcart import database
from smartcart.main import app
from smartcart.optimizer import BasketOptimizer
from smartcart.security import limiter
from tests.auth_utils import auth_headers, make_token
from tests.test_real_data import RealDataTestCase

ADMIN = {"X-Admin-Token": "test-admin-token"}


class ApiTestCase(RealDataTestCase):
    def setUp(self):
        super().setUp()
        database.load_real_stores(self.conn, "edmonton")
        self.client = TestClient(app)
        self.store_id = self.first_store_id()
        self.butter = self.product_id("Salted Butter")
        self.today = local_today().isoformat()

    def submit(self, headers, **overrides):
        body = {"store_id": self.store_id, "price": 5.49, "item_name": "salted butter",
                "observed_on": self.today, "source": "receipt"}
        body.update(overrides)
        return self.client.post("/api/prices/observations", json=body, headers=headers)


class TestTokenVerification(ApiTestCase):
    def test_missing_token_is_401(self):
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_expired_token_is_401(self):
        headers = {"Authorization": f"Bearer {make_token('u1', expires_in=-60)}"}
        self.assertEqual(self.client.get("/api/me", headers=headers).status_code, 401)

    def test_wrong_signature_is_401(self):
        headers = {"Authorization": f"Bearer {make_token('u1', secret='x' * 40)}"}
        self.assertEqual(self.client.get("/api/me", headers=headers).status_code, 401)

    def test_wrong_audience_is_401(self):
        headers = {"Authorization": f"Bearer {make_token('u1', audience='anon')}"}
        self.assertEqual(self.client.get("/api/me", headers=headers).status_code, 401)

    def test_valid_token_creates_user(self):
        res = self.client.get("/api/me", headers=auth_headers("u-new", email="new@example.com"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["email"], "new@example.com")
        self.assertEqual(res.json()["plan"], "free")


class TestPriceSubmissions(ApiTestCase):
    def test_submission_updates_shared_price(self):
        res = self.submit(auth_headers("shopper-1"))
        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(res.json()["status"], "accepted")
        self.assertEqual(res.json()["product_id"], self.butter)

        prices = self.client.get(f"/api/stores/{self.store_id}/prices").json()["prices"]
        self.assertEqual(len(prices), 1)
        self.assertAlmostEqual(prices[0]["price"], 5.49)
        self.assertEqual(prices[0]["observation_count"], 1)

    def test_anonymous_submission_rejected(self):
        self.assertEqual(self.submit({}).status_code, 401)

    def test_validation(self):
        h = auth_headers("shopper-2")
        self.assertEqual(self.submit(h, price=0.01).status_code, 422)
        self.assertEqual(self.submit(h, store_id=999999).status_code, 404)
        future = (local_today() + datetime.timedelta(days=5)).isoformat()
        self.assertEqual(self.submit(h, observed_on=future).status_code, 422)
        old = (local_today() - datetime.timedelta(days=60)).isoformat()
        self.assertEqual(self.submit(h, observed_on=old).status_code, 422)
        self.assertEqual(self.submit(h, item_name="xyzzy widget").status_code, 422)

    def test_outlier_is_held_for_review_then_moderated(self):
        for i in range(3):
            self.submit(auth_headers(f"regular-{i}"), price=5.49)
        outlier = self.submit(auth_headers("outlier"), price=49.99)
        self.assertEqual(outlier.json()["status"], "pending")
        prices = self.client.get(f"/api/stores/{self.store_id}/prices").json()["prices"]
        self.assertAlmostEqual(prices[0]["price"], 5.49)

        pending = self.client.get("/api/admin/observations", headers=ADMIN).json()["observations"]
        self.assertEqual([o["id"] for o in pending], [outlier.json()["id"]])
        self.assertEqual(self.client.get("/api/admin/observations", headers=auth_headers("x")).status_code, 403)

        res = self.client.post(f"/api/admin/observations/{outlier.json()['id']}", json={"status": "rejected"}, headers=ADMIN)
        self.assertEqual(res.status_code, 200)
        trust = self.conn.execute("SELECT trust_score FROM users WHERE id = 'outlier'").fetchone()["trust_score"]
        self.assertLess(trust, 0.5)

    def test_users_manage_only_their_own_reports(self):
        mine = self.submit(auth_headers("owner")).json()["id"]
        listed = self.client.get("/api/prices/observations/mine", headers=auth_headers("owner")).json()["observations"]
        self.assertEqual([o["id"] for o in listed], [mine])
        self.assertEqual(self.client.delete(f"/api/prices/observations/{mine}", headers=auth_headers("intruder")).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/prices/observations/{mine}", headers=auth_headers("owner")).status_code, 200)
        self.assertEqual(self.client.get(f"/api/stores/{self.store_id}/prices").json()["prices"], [])

    def test_product_catalog_search(self):
        products = self.client.get("/api/products?q=butter").json()["products"]
        self.assertTrue(any(p["name"] == "Salted Butter" for p in products))


class TestAccount(ApiTestCase):
    def test_profile_update_records_marketing_consent_time(self):
        h = auth_headers("profile-user")
        res = self.client.patch("/api/me", headers=h, json={"display_name": "Sam", "home_postal_code": "t6e 2a1",
                                                             "marketing_opt_in": True})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["home_postal_code"], "T6E2A1")
        self.assertTrue(body["marketing_opt_in"])
        self.assertIsNotNone(body["marketing_opt_in_at"])

    def test_export_and_delete(self):
        h = auth_headers("leaving-user")
        self.submit(h)
        self.client.post("/api/alerts", headers=h, json={"product_name": "eggs"})
        self.client.post("/api/savings/receipts", headers=h, json={
            "store_name": "Safeway", "trip_date": self.today, "amount_spent": 10, "regular_amount": 12})

        export = self.client.get("/api/me/export", headers=h).json()
        self.assertEqual(len(export["price_observations"]), 1)
        self.assertEqual(len(export["sale_alerts"]), 1)
        self.assertEqual(len(export["receipts"]), 1)

        res = self.client.delete("/api/me", headers=h)
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(self.conn.execute("SELECT id FROM users WHERE id = 'leaving-user'").fetchone())
        for table in ("receipts", "sale_alerts"):
            n = self.conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id = 'leaving-user'").fetchone()["n"]
            self.assertEqual(n, 0)
        # The price report survives, de-identified, so shared prices stay accurate.
        obs = self.conn.execute("SELECT submitted_by FROM price_observations").fetchall()
        self.assertEqual([o["submitted_by"] for o in obs], [None])
        self.assertEqual(len(self.client.get(f"/api/stores/{self.store_id}/prices").json()["prices"]), 1)


class TestShoppingList(ApiTestCase):
    def test_list_round_trip_is_private_and_deleted_with_account(self):
        alice, bob = auth_headers("alice"), auth_headers("bob")
        self.assertEqual(self.client.get("/api/me/list", headers=alice).json(), {"items": [], "updated_at": None})
        items = [{"id": "a1", "name": "Salted butter", "quantity": 2}, {"id": "a2", "name": "Eggs", "quantity": 1}]
        saved = self.client.put("/api/me/list", json={"items": items}, headers=alice)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.client.get("/api/me/list", headers=alice).json()["items"], items)
        self.assertEqual(self.client.get("/api/me/list", headers=bob).json()["items"], [])
        self.assertEqual(self.client.get("/api/me/export", headers=alice).json()["shopping_lists"][0]["user_id"], "alice")

        self.client.delete("/api/me", headers=alice)
        self.assertEqual(self.client.get("/api/me/list", headers=alice).json()["items"], [])

    def test_list_validation(self):
        h = auth_headers("carol")
        self.assertEqual(self.client.get("/api/me/list").status_code, 401)
        too_many = [{"id": str(i), "name": "x", "quantity": 1} for i in range(201)]
        self.assertEqual(self.client.put("/api/me/list", json={"items": too_many}, headers=h).status_code, 422)
        bad_qty = [{"id": "1", "name": "milk", "quantity": 0}]
        self.assertEqual(self.client.put("/api/me/list", json={"items": bad_qty}, headers=h).status_code, 422)


class TestOwnerAdmin(ApiTestCase):
    def test_allowlisted_email_becomes_admin_with_full_access(self):
        me = self.client.get("/api/me", headers=auth_headers("owner-id", email="Owner@Example.com")).json()
        self.assertTrue(me["is_admin"])
        self.assertTrue(me["has_full_access"])
        self.assertEqual(me["plan"], "admin")
        # Admin endpoints work with the account alone, no admin token needed.
        self.assertEqual(self.client.get("/api/admin/observations", headers=auth_headers("owner-id", email="owner@example.com")).status_code, 200)

    def test_other_emails_are_regular_users(self):
        me = self.client.get("/api/me", headers=auth_headers("someone", email="someone@example.com")).json()
        self.assertFalse(me["is_admin"])
        self.assertFalse(me["has_full_access"])
        self.assertEqual(self.client.get("/api/admin/observations", headers=auth_headers("someone", email="someone@example.com")).status_code, 403)

    def test_admin_reports_skip_review_and_rate_limit(self):
        owner = auth_headers("owner-id", email="owner@example.com")
        for i in range(3):
            self.submit(auth_headers(f"regular-{i}"), price=5.49)
        self.assertEqual(self.submit(owner, price=49.99).json()["status"], "accepted")

        limiter.enabled = True
        limiter.reset()
        try:
            codes = [self.submit(owner).status_code for _ in range(65)]
        finally:
            limiter.enabled = False
            limiter.reset()
        self.assertNotIn(429, codes)


class TestAdminFlyers(ApiTestCase):
    def flyer(self, **overrides):
        body = {
            "banner": "No Frills", "title": "Weekly Flyer",
            "valid_from": self.today, "valid_to": (local_today() + datetime.timedelta(days=6)).isoformat(),
            "deals": [{"title": "Salted Butter 454g", "category": "Dairy", "sale_price": 4.99, "original_price": 6.99}],
        }
        body.update(overrides)
        return body

    def test_admin_creates_flyer_visible_to_everyone(self):
        res = self.client.post("/api/admin/flyers", json=self.flyer(), headers=ADMIN)
        self.assertEqual(res.status_code, 201, res.text)
        flyers = self.client.get("/api/flyers").json()["flyers"]
        self.assertEqual(len(flyers), 1)
        deals = self.client.get(f"/api/flyers/{flyers[0]['id']}/deals").json()["deals"]
        self.assertEqual(deals[0]["price"], 4.99)
        self.assertEqual(self.client.delete(f"/api/admin/flyers/{flyers[0]['id']}", headers=ADMIN).status_code, 200)
        self.assertEqual(self.client.get("/api/flyers").json()["flyers"], [])

    def test_non_admin_and_bad_dates_rejected(self):
        self.assertEqual(self.client.post("/api/admin/flyers", json=self.flyer(), headers=auth_headers("u")).status_code, 403)
        bad = self.flyer(valid_to="2020-01-01")
        self.assertEqual(self.client.post("/api/admin/flyers", json=bad, headers=ADMIN).status_code, 422)

    def test_unknown_chain_rejected_and_names_canonicalised(self):
        self.assertEqual(self.client.post("/api/admin/flyers", json=self.flyer(banner="Nofrills"), headers=ADMIN).status_code, 422)
        self.assertEqual(self.client.post("/api/admin/flyers", json=self.flyer(banner="no frills "), headers=ADMIN).status_code, 201)
        self.assertEqual(self.client.get("/api/flyers").json()["flyers"][0]["banner"], "No Frills")
        self.assertIn("No Frills", self.client.get("/api/admin/banners", headers=ADMIN).json()["banners"])

    def test_flyer_deal_lowers_trip_plan_price_at_that_chain(self):
        stores = self.conn.execute("SELECT id FROM stores WHERE banner = 'No Frills'").fetchall()
        other = self.conn.execute("SELECT id FROM stores WHERE banner != 'No Frills' LIMIT 1").fetchone()["id"]
        h = auth_headers("shopper")
        for store in [stores[0]["id"], other]:
            self.assertEqual(self.submit(h, store_id=store, price=6.49).status_code, 201)
        self.assertEqual(self.client.post("/api/admin/flyers", json=self.flyer(), headers=ADMIN).status_code, 201)

        res = self.client.post("/api/optimize", json={"items": [{"name": "salted butter", "quantity": 1}],
                                                      "postal_code": "T6E 2A1", "max_radius_km": 60})
        self.assertEqual(res.status_code, 200, res.text)
        plan = res.json()["plans"]["best_single_run"]
        item = plan["stores"][0]["items"][0]
        self.assertEqual(item["package_price"], 4.99)
        self.assertTrue(item["on_sale"])
        self.assertEqual(plan["stores"][0]["chain"], "No Frills")

    def test_admin_role_on_user_account(self):
        self.client.get("/api/me", headers=auth_headers("staff"))
        self.conn.execute("UPDATE users SET is_admin = 1 WHERE id = 'staff'")
        self.conn.commit()
        res = self.client.post("/api/admin/flyers", json=self.flyer(), headers=auth_headers("staff"))
        self.assertEqual(res.status_code, 201)


class TestCompareHonesty(ApiTestCase):
    def test_compare_reports_freshness_and_never_invents_stores(self):
        self.submit(auth_headers("cmp-user"), price=5.49)
        # A flyer deal from a chain with no store in the data must not appear as a made-up store.
        self.client.post("/api/admin/flyers", headers=ADMIN, json={
            "banner": "Nonexistent Grocer", "title": "Flyer", "valid_from": self.today, "valid_to": self.today,
            "deals": [{"title": "Salted Butter 454g", "category": "Dairy", "sale_price": 1.99}],
        })
        data = self.client.get("/api/v1/search/compare?q=butter&postal_code=T6E2A1").json()["data"]
        butter = next(d for d in data if d["product_id"] == self.butter)
        banners = {st["banner"] for st in butter["stores"]}
        self.assertNotIn("Nonexistent Grocer", banners)
        entry = next(st for st in butter["stores"] if st["store_id"] == self.store_id)
        self.assertEqual(entry["observation_count"], 1)
        self.assertIsNotNone(entry["last_observed_at"])

    def nofrills(self):
        return [r["id"] for r in self.conn.execute(
            "SELECT id FROM stores WHERE banner = 'No Frills' ORDER BY id").fetchall()]

    def test_chain_price_fills_other_stores_with_where_it_was_seen(self):
        reported, other = self.nofrills()[:2]
        self.assertEqual(self.submit(auth_headers("chain-user"), store_id=reported, price=5.29).status_code, 201)
        reported_name = self.conn.execute("SELECT name FROM stores WHERE id = ?", (reported,)).fetchone()["name"]

        basket = BasketOptimizer().prepare_basket_data([{"name": "salted butter", "quantity": 1}],
                                                       [{"id": other, "banner": "No Frills"}])
        filled = basket["items"][0]["prices"][other]
        self.assertEqual(filled["price"], 5.29)
        self.assertEqual(filled["in_stock"], 0)  # not confirmed at this store
        self.assertTrue(filled["reported_at"].startswith(reported_name))

    def test_store_own_report_beats_chain_price(self):
        a, b = self.nofrills()[:2]
        h = auth_headers("chain-user-2")
        self.submit(h, store_id=a, price=4.00)
        self.submit(h, store_id=b, price=6.00)
        price = BasketOptimizer().prepare_basket_data([{"name": "salted butter"}],
                                                      [{"id": b, "banner": "No Frills"}])["items"][0]["prices"][b]
        self.assertEqual(price["price"], 6.00)
        self.assertIsNone(price.get("reported_at"))

    def test_expired_flyers_and_dearer_deals_are_not_sales(self):
        self.submit(auth_headers("cmp-2"), price=3.49)
        banner = self.conn.execute("SELECT banner FROM stores WHERE id = ?", (self.store_id,)).fetchone()["banner"]
        # A deal pricier than the reported price isn't shown as a sale.
        self.client.post("/api/admin/flyers", headers=ADMIN, json={
            "banner": banner, "title": "Flyer", "valid_from": self.today, "valid_to": self.today,
            "deals": [{"title": "Salted Butter 454g", "category": "Dairy", "sale_price": 3.99}],
        })
        # An expired flyer is ignored even though it's cheaper.
        self.conn.execute("INSERT INTO flyers (banner, title, valid_from, valid_to) VALUES (?, 'Old', '2020-01-01', '2020-01-07')", (banner,))
        old_id = self.conn.execute("SELECT MAX(id) AS id FROM flyers").fetchone()["id"]
        self.conn.execute("INSERT INTO flyer_deals (flyer_id, product_id, title, category, sale_price) VALUES (?, ?, 'Salted Butter', 'Dairy', 0.99)",
                          (old_id, self.butter))
        self.conn.commit()
        data = self.client.get("/api/v1/search/compare?q=butter&postal_code=T6E2A1").json()["data"]
        entry = next(st for st in next(d for d in data if d["product_id"] == self.butter)["stores"] if st["banner"] == banner)
        self.assertEqual(entry["price"], 3.49)
        self.assertFalse(entry["is_on_sale"])


class TestHttpHardening(ApiTestCase):
    def test_security_headers(self):
        res = self.client.get("/api/coverage/stats")
        self.assertEqual(res.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(res.headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'none'", res.headers["Content-Security-Policy"])

    def test_web_pages_get_a_strict_csp(self):
        csp = self.client.get("/config.js").headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertNotIn("'unsafe-eval'", csp.replace("'wasm-unsafe-eval'", ""))

    def test_healthz(self):
        self.assertEqual(self.client.get("/healthz").json(), {"status": "ok"})

    def test_oversized_body_rejected(self):
        res = self.client.post("/api/recipes/parse", content=b"x" * (9 * 1024 * 1024),
                               headers={"Content-Type": "application/json"})
        self.assertEqual(res.status_code, 413)

    def test_oversized_chunked_body_rejected(self):
        def chunks():
            for _ in range(10):
                yield b"x" * (1024 * 1024)
        res = self.client.post("/api/recipes/parse", content=chunks(), headers={"Content-Type": "application/json"})
        self.assertEqual(res.status_code, 413)

    def test_price_submissions_are_rate_limited(self):
        limiter.enabled = True
        limiter.reset()
        try:
            h = auth_headers("spammer")
            codes = [self.submit(h).status_code for _ in range(62)]
        finally:
            limiter.enabled = False
            limiter.reset()
        self.assertIn(429, codes)
        self.assertEqual(codes[:60].count(201), 60)


if __name__ == "__main__":
    unittest.main()
