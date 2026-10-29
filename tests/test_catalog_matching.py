"""
Catalog matching regression table: what shoppers type on their lists and what
receipts print, and the product each should land on.
"""

from smartcart import normalizer
from smartcart.catalog import PRODUCT_CATALOG
from smartcart.database import seed_product_catalog
from tests.test_real_data import RealDataTestCase

EXPECTED = {
    # List items
    "milk": "2% Partly Skimmed Milk",
    "homo milk": "Homogenized Milk 3.25%",
    "almond milk": "Unsweetened Almond Beverage",
    "chocolate milk": "Chocolate Milk",
    "butter": "Salted Butter",
    "unsalted butter": "Unsalted Butter",
    "peanut butter": "Peanut Butter",
    "cheese": "Cheddar Cheese Block",
    "cream cheese": "Cream Cheese",
    "cottage cheese": "Cottage Cheese",
    "sour cream": "Sour Cream",
    "ice cream": "Ice Cream",
    "whipping cream": "Heavy Whipping Cream 33%",
    "eggs": "Large Grade A White Eggs (12-pack)",
    "chicken": "Boneless Skinless Chicken Thighs",
    "chicken breast": "Boneless Skinless Chicken Breasts",
    "chicken broth": "Chicken Broth",
    "chicken noodle soup": "Chicken Noodle Soup",
    "ground beef": "Lean Ground Beef",
    "apples": "Gala Apples",
    "orange juice": "Orange Juice",
    "tomatoes": "Tomatoes on the Vine",
    "tomato paste": "Tomato Paste",
    "canned tomatoes": "Canned Crushed Tomatoes",
    "potatoes": "Russet Potatoes (10 lb bag)",
    "sweet potatoes": "Sweet Potatoes",
    "green onions": "Green Onions",
    "pepper": "Ground Black Pepper",
    "red pepper": "Red Bell Pepper",
    "rice": "Long Grain Basmati Rice",
    "pasta": "Dry Spaghetti",
    "bread": "White Sliced Sandwich Bread",
    "salmon": "Fresh Atlantic Salmon Fillets",
    "canned salmon": "Canned Salmon",
    "chips": "Potato Chips",
    "tortilla chips": "Tortilla Chips",
    # Receipt lines
    "SALTED BUTTER 454G": "Salted Butter",
    "LARGE EGGS 12PK": "Large Grade A White Eggs (12-pack)",
    "WHITE BREAD 675G": "White Sliced Sandwich Bread",
    "2% MILK 4L": "2% Partly Skimmed Milk",
    "1% MILK 4L": "1% Partly Skimmed Milk",
    "HOMO MILK 4L": "Homogenized Milk 3.25%",
    "OJ 1.54L": "Orange Juice",
    "PC BACON 375G": "Bacon",
    "KRAFT DINNER": "Macaroni and Cheese Dinner",
    "TOILET PAPER 12DR": "Toilet Paper (12 double rolls)",
    "GRND BEEF LEAN": "Lean Ground Beef",
    "CHKN WINGS": "Chicken Wings",
}


class TestCatalogMatching(RealDataTestCase):
    def setUp(self):
        super().setUp()
        normalizer._PRODUCT_CATALOG_CACHE = None

    def test_list_items_and_receipt_lines_match_the_right_product(self):
        wrong = {}
        for query, expected in EXPECTED.items():
            match = normalizer.match_product_in_catalog(query)
            got = match["name"] if match else None
            if got != expected:
                wrong[query] = got
        self.assertEqual(wrong, {})

    def test_catalog_rows_are_consistent(self):
        names = [row[0] for row in PRODUCT_CATALOG]
        self.assertEqual(len(names), len(set(names)))
        for name, _cat, _brand, qty, _unit, standard, amount, aliases in PRODUCT_CATALOG:
            self.assertGreater(qty, 0, name)
            self.assertGreater(amount, 0, name)
            self.assertIn(standard, {"weight_100g", "volume_100ml", "unit"}, name)
            self.assertTrue(aliases.strip(), name)

    def test_seeding_adds_only_missing_products(self):
        self.assertEqual(seed_product_catalog(self.conn), 0)
        self.conn.execute("DELETE FROM products WHERE name = 'Bacon'")
        self.conn.commit()
        self.assertEqual(seed_product_catalog(self.conn), 1)
