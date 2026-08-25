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
        self.assertTrue(res_bc["supported"])
        self.assertEqual(res_bc["province"], "British Columbia")

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


    def test_dinner_deals_endpoints(self):
        res = self.client.get("/api/recipes/dinner-deals")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["count"], 5)
        first = data["recipes"][0]
        self.assertIn("cost_per_serving", first)
        self.assertIn("ingredients", first)

        res_single = self.client.get(f"/api/recipes/dinner-deals/{first['id']}")
        self.assertEqual(res_single.status_code, 200)
        self.assertEqual(res_single.json()["id"], first["id"])

    def test_coverage_and_ticker_endpoints(self):
        res_cov = self.client.get("/api/coverage/stats")
        self.assertEqual(res_cov.status_code, 200)
        self.assertGreaterEqual(res_cov.json()["total_stores_tracked"], 2000)

        res_tick = self.client.get("/api/deals/top-ticker")
        self.assertEqual(res_tick.status_code, 200)
        self.assertGreaterEqual(len(res_tick.json()["deals"]), 5)

    def test_barcode_lookup_and_samples(self):
        res_samples = self.client.get("/api/barcodes/samples")
        self.assertEqual(res_samples.status_code, 200)
        samples = res_samples.json()["samples"]
        self.assertGreaterEqual(len(samples), 5)

        # Look up the Italpasta Fusilli barcode
        res_code = self.client.get("/api/barcode/lookup?barcode=068113112345")
        self.assertEqual(res_code.status_code, 200)
        data = res_code.json()
        self.assertTrue(data["found"])
        self.assertEqual(data["name"], "Italpasta Fusilli Pasta")
        self.assertIn("nutrition", data)
        self.assertIn("store_prices", data)

    def test_savings_summary_and_receipts(self):
        res_sum = self.client.get("/api/savings/summary")
        self.assertEqual(res_sum.status_code, 200)
        summary = res_sum.json()
        self.assertGreater(summary["total_saved"], 0)
        self.assertGreater(summary["trips_count"], 0)

        res_receipts = self.client.get("/api/savings/receipts")
        self.assertEqual(res_receipts.status_code, 200)
        self.assertGreaterEqual(len(res_receipts.json()["receipts"]), 1)

    def test_sale_alerts(self):
        res_alerts = self.client.get("/api/alerts")
        self.assertEqual(res_alerts.status_code, 200)
        alerts = res_alerts.json()["alerts"]
        self.assertGreaterEqual(len(alerts), 1)

    def test_regional_coverage_and_flyers(self):
        res_reg = self.client.get("/api/coverage/regions")
        self.assertEqual(res_reg.status_code, 200)
        data = res_reg.json()
        self.assertIn("Alberta", data["regions"])
        self.assertIn("British Columbia", data["regions"])

        # Test Calgary flyers
        res_calgary = self.client.get("/api/flyers?city=Calgary")
        self.assertEqual(res_calgary.status_code, 200)
        flyers = res_calgary.json()["flyers"]
        self.assertGreaterEqual(len(flyers), 5)

        # Test Vancouver flyers
        res_van = self.client.get("/api/flyers?city=Vancouver")
        self.assertEqual(res_van.status_code, 200)
        self.assertGreaterEqual(len(res_van.json()["flyers"]), 5)

    def test_sync_status_and_refresh(self):
        res_status = self.client.get("/api/sync/status")
        self.assertEqual(res_status.status_code, 200)
        data = res_status.json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["stores_indexed"], 3524)
        self.assertIn("flyer_cycle", data)
        self.assertIn("gas_prices", data)

        res_refresh = self.client.post("/api/sync/refresh")
        self.assertEqual(res_refresh.status_code, 200)
        ref_data = res_refresh.json()
        self.assertEqual(ref_data["status"], "SUCCESS")
        self.assertEqual(ref_data["stores_count"], 3524)

class TestSmartCartEnhancementsTDD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        seed_edmonton_data()
        cls.client = TestClient(app)

    def test_barcode_normalization_logic(self):
        from smartcart.normalizer import normalize_barcode
        # 12-digit standard UPC-A
        self.assertEqual(normalize_barcode("068700011078"), "068700011078")
        # 13-digit EAN-13 starting with zero (padded UPC-A) -> stripped to 12 digits
        self.assertEqual(normalize_barcode("0068700011078"), "068700011078")
        # Input with spaces and dashes
        self.assertEqual(normalize_barcode(" 068700-011078 "), "068700011078")
        # Standard 13-digit European EAN-13 not starting with 0
        self.assertEqual(normalize_barcode("8001234567890"), "8001234567890")

    def test_flyer_deals_structured_columns(self):
        conn = get_connection()
        c = conn.cursor()
        c.execute("PRAGMA table_info(flyer_deals)")
        columns = {row["name"] for row in c.fetchall()}
        conn.close()
        required_cols = {"store_name", "title", "sale_price", "unit_size", "valid_until", "category"}
        self.assertTrue(required_cols.issubset(columns), f"Missing columns in flyer_deals: {required_cols - columns}")

    def test_barcode_resolve_api_v1(self):
        # Resolve sample barcode (Italpasta Fusilli 068113112345)
        res = self.client.get("/api/v1/barcodes/resolve/068113112345")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("data", body)
        data = body["data"]
        self.assertTrue(data.get("found", True))
        self.assertEqual(data["name"], "Italpasta Fusilli Pasta")
        self.assertIn("brand", data)
        self.assertIn("package_size", data)
        self.assertIn("nutrition", data)
        self.assertIn("store_prices", data)
        self.assertGreaterEqual(len(data["store_prices"]), 1)

    def test_flyer_grounded_recipes_api_v1(self):
        res = self.client.get("/api/v1/recipes/flyer-grounded?city=Edmonton")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("data", body)
        recipes = body["data"]
        self.assertGreaterEqual(len(recipes), 1)
        
        recipe = recipes[0]
        self.assertIn("title", recipe)
        self.assertIn("total_sale_cost", recipe)
        self.assertIn("total_regular_cost", recipe)
        self.assertIn("total_savings", recipe)
        self.assertIn("ingredients", recipe)
        
        # At least one ingredient must be annotated as on sale with store metadata
        has_sale_ing = any(ing.get("is_on_sale") and ing.get("store_name") for ing in recipe["ingredients"])
        self.assertTrue(has_sale_ing, "Recipe must annotate ingredients on sale with store_name")

    def test_multi_store_compare_search_api_v1(self):
        res = self.client.get("/api/v1/search/compare?q=chicken&city=Edmonton")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("data", body)
        items = body["data"]
        self.assertGreaterEqual(len(items), 1)

        first_group = items[0]
        self.assertIn("name", first_group)
        self.assertIn("stores", first_group)
        self.assertGreaterEqual(len(first_group["stores"]), 1)
        
        first_store = first_group["stores"][0]
        self.assertIn("store_name", first_store)
        self.assertIn("banner", first_store)
        self.assertIn("price", first_store)
        self.assertIn("unit_price_display", first_store)
        self.assertIn("is_lowest", first_store)

    def test_barcode_resolve_invalid_format(self):
        # Non-alphanumeric barcode yields 400
        res = self.client.get("/api/v1/barcodes/resolve/---")
        self.assertEqual(res.status_code, 400)

    def test_multi_store_compare_search_staples(self):
        # Search for oats or milk
        res = self.client.get("/api/v1/search/compare?q=milk&city=Calgary")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("data", body)
        self.assertGreaterEqual(len(body["data"]), 1)

    def test_flyer_deals_endpoint_has_all_six_structured_fields(self):
        res = self.client.get("/api/flyers/deals")
        self.assertEqual(res.status_code, 200)
        deals = res.json().get("deals", [])
        self.assertGreater(len(deals), 0)
        first = deals[0]
        for field in ["store_name", "item_name", "sale_price", "unit_size", "valid_until", "category"]:
            self.assertIn(field, first, f"Field {field} must be present in flyer deal")
            self.assertIsNotNone(first[field], f"Field {field} must not be None")

    def test_meal_plan_generate_post_endpoint(self):
        payload = {
            "days": ["Thursday", "Friday", "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday"],
            "servings": 4
        }
        res = self.client.post("/api/meal-plan/generate", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("meal_plan", data)
        self.assertIn("summary", data)
        for day in payload["days"]:
            self.assertIn(day, data["meal_plan"])
            meal = data["meal_plan"][day]
            self.assertIn("title", meal)
            self.assertIn("cost_per_serving", meal)
            self.assertIn("ingredients", meal)
            self.assertGreater(len(meal["ingredients"]), 0)

if __name__ == "__main__":
    unittest.main()

