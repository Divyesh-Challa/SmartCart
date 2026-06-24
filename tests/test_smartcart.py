"""
Automated Test Suite for SmartCart
Covers database seeding, recipe parsing, unit price normalization,
postal code geocoding, Edmonton-wide stores, and interactive weekly digital circulars.
"""

import unittest
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from smartcart.database import init_db, seed_edmonton_data, get_connection, haversine_distance_km
from smartcart.parser import parse_ingredient_line, parse_recipe_text
from smartcart.normalizer import (
    normalize_quantity_to_standard,
    match_product_in_catalog,
    compute_packages_needed,
    get_product_prices_across_stores
)
from smartcart.geocoding import resolve_postal_code
from smartcart.optimizer import BasketOptimizer
from fastapi.testclient import TestClient
from smartcart.main import app

class TestSmartCartDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        seed_edmonton_data()

    def test_stores_seeded_edmonton_wide(self):
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM stores")
        count = c.fetchone()["cnt"]
        c.execute("SELECT DISTINCT quadrant FROM stores")
        quadrants = {row["quadrant"] for row in c.fetchall()}
        conn.close()
        self.assertGreaterEqual(count, 20)
        self.assertTrue({"Central", "South", "West", "East", "North"}.issubset(quadrants))

    def test_products_and_flyers_seeded(self):
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM products")
        self.assertGreaterEqual(c.fetchone()["cnt"], 20)
        c.execute("SELECT COUNT(*) as cnt FROM flyers")
        self.assertGreaterEqual(c.fetchone()["cnt"], 5)
        c.execute("SELECT COUNT(*) as cnt FROM flyer_deals")
        self.assertGreaterEqual(c.fetchone()["cnt"], 15)
        conn.close()

    def test_haversine_distance(self):
        dist = haversine_distance_km(53.5461, -113.4938, 53.5606, -113.5137)
        self.assertGreater(dist, 1.5)
        self.assertLess(dist, 4.0)

class TestSmartCartParser(unittest.TestCase):
    def test_single_ingredient_parsing(self):
        line = "1 kg boneless skinless chicken thighs (diced)"
        parsed = parse_ingredient_line(line)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["quantity"], 1.0)
        self.assertEqual(parsed["unit"], "kg")
        self.assertIn("chicken thighs", parsed["name"].lower())

    def test_fraction_parsing(self):
        line = "1 1/2 cups heavy whipping cream"
        parsed = parse_ingredient_line(line)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["quantity"], 1.5)
        self.assertEqual(parsed["unit"], "cup")

    def test_multi_line_recipe_parsing(self):
        recipe = """
        * 1 kg chicken breasts
        * 2 cans crushed tomatoes
        * 1 yellow onion
        * 4 cloves garlic
        """
        items = parse_recipe_text(recipe)
        self.assertEqual(len(items), 4)

class TestSmartCartNormalizer(unittest.TestCase):
    def test_weight_normalization(self):
        std_type, norm_amt = normalize_quantity_to_standard(1.0, "kg")
        self.assertEqual(std_type, "weight_100g")
        self.assertAlmostEqual(norm_amt, 10.0, places=2)

    def test_volume_normalization(self):
        std_type, norm_amt = normalize_quantity_to_standard(4.0, "L")
        self.assertEqual(std_type, "volume_100ml")
        self.assertAlmostEqual(norm_amt, 40.0, places=2)

    def test_catalog_matching(self):
        match1 = match_product_in_catalog("chicken thighs")
        self.assertIsNotNone(match1)
        self.assertEqual(match1["name"], "Boneless Skinless Chicken Thighs")

class TestGeocodingAndLocation(unittest.TestCase):
    def test_postal_code_resolution(self):
        res1 = resolve_postal_code("T6E 2A1")
        self.assertIsNotNone(res1)
        self.assertEqual(res1["postal_code"], "T6E 2A1")
        self.assertTrue(res1["supported"])

        res_bc = resolve_postal_code("V6B 1A1")
        self.assertIsNotNone(res_bc)
        self.assertFalse(res_bc["supported"])
        self.assertIn("British Columbia", res_bc["message"])

class TestFlyersAndDeals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_get_flyers(self):
        res = self.client.get("/api/flyers")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(len(data["flyers"]), 5)
        banners = [f["banner"] for f in data["flyers"]]
        self.assertIn("No Frills", banners)
        self.assertIn("Walmart", banners)

    def test_get_flyer_deals_with_filter(self):
        res = self.client.get("/api/flyers/deals?banner=No%20Frills")
        self.assertEqual(res.status_code, 200)
        deals = res.json()["deals"]
        self.assertGreater(len(deals), 0)
        self.assertTrue(all(d["banner"] == "No Frills" for d in deals))

    def test_optimize_basket_with_postal_code(self):
        res = self.client.post("/api/basket/optimize", json={
            "items": [
                {"name": "chicken thighs", "quantity": 1.0, "unit": "kg"},
                {"name": "bananas", "quantity": 1.0, "unit": "kg"}
            ],
            "postal_code": "T6E 2A1",
            "exclude_membership": True,
            "max_radius_km": 15.0
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("plans", data)


    def test_gas_price_endpoint_and_service(self):
        res = self.client.get("/api/gas-price")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("price_per_litre", data)
        self.assertEqual(data["city"], "Edmonton")
        self.assertGreater(data["price_per_litre"], 0.5)

if __name__ == "__main__":
    unittest.main()
