"""
The product catalog: generic grocery items shoppers can report prices for.

These are product definitions only (name, typical Canadian package size and the
words people use for it). Prices never live here; they come from shoppers'
reports and flyers. Receipt lines and list items are matched against the
names and aliases, so aliases should be what people write or what receipts print.
"""

from typing import List, Tuple

CatalogRow = Tuple[str, str, str, float, str, str, float, str]


def _item(name: str, category: str, quantity: float, unit: str, aliases: str, brand: str = "Generic") -> CatalogRow:
    """Builds a catalog row, working out the standard unit used for unit prices."""
    unit_key = unit.lower()
    if unit_key == "kg":
        standard, amount = "weight_100g", quantity * 10
    elif unit_key == "g":
        standard, amount = "weight_100g", quantity / 100
    elif unit_key == "l":
        standard, amount = "volume_100ml", quantity * 10
    elif unit_key == "ml":
        standard, amount = "volume_100ml", quantity / 100
    elif unit_key == "unit":
        standard, amount = "unit", quantity
    else:
        raise ValueError(f"unknown unit {unit!r} for {name}")
    return (name, category, brand, quantity, unit, standard, round(amount, 2), aliases)


# The original staples (unchanged: existing price reports point at these names).
STAPLES: List[CatalogRow] = [
    ("Boneless Skinless Chicken Breasts", "Meat", "Generic", 1.0, "kg", "weight_100g", 10.0, "chicken breast, chicken breasts, chicken cutlets"),
    ("Boneless Skinless Chicken Thighs", "Meat", "Generic", 1.0, "kg", "weight_100g", 10.0, "chicken thighs, chicken thigh, chicken"),
    ("Lean Ground Beef", "Meat", "Generic", 1.0, "kg", "weight_100g", 10.0, "ground beef, minced beef, beef"),
    ("Fresh Atlantic Salmon Fillets", "Seafood", "Generic", 500.0, "g", "weight_100g", 5.0, "salmon, salmon fillet, fish"),
    ("2% Partly Skimmed Milk", "Dairy", "Dairyland", 4.0, "L", "volume_100ml", 40.0, "milk, 2% milk, cow milk"),
    ("Large Grade A White Eggs (12-pack)", "Dairy", "Generic", 12.0, "unit", "unit", 12.0, "eggs, egg, large eggs, dozen eggs"),
    ("Large Grade A White Eggs (30-pack)", "Dairy", "Generic", 30.0, "unit", "unit", 30.0, "eggs, egg, flat eggs, 30 eggs"),
    ("Salted Butter", "Dairy", "Generic", 454.0, "g", "weight_100g", 4.54, "butter, salted butter, baking butter"),
    ("Greek Yogurt Plain 0%", "Dairy", "Oikos", 750.0, "g", "weight_100g", 7.5, "greek yogurt, yogurt, plain yogurt"),
    ("Cheddar Cheese Block", "Dairy", "Kraft / Black Diamond", 400.0, "g", "weight_100g", 4.0, "cheddar cheese, cheese, cheese block"),
    ("Heavy Whipping Cream 33%", "Dairy", "Dairyland", 500.0, "ml", "volume_100ml", 5.0, "heavy cream, whipping cream, 35% cream"),
    ("Bananas", "Produce", "Cavendish", 1.0, "kg", "weight_100g", 10.0, "banana, bananas, fresh bananas"),
    ("Avocados (Bag of 5)", "Produce", "Generic", 5.0, "unit", "unit", 5.0, "avocado, avocados, ripe avos, avo"),
    ("Pineapple", "Produce", "Del Monte", 1.0, "unit", "unit", 1.0, "pineapple, pineapples, fresh pineapple"),
    ("Yellow Onions (3 lb bag)", "Produce", "Generic", 1.36, "kg", "weight_100g", 13.6, "onions, onion, yellow onion"),
    ("Baby Spinach", "Produce", "Organic Girl", 312.0, "g", "weight_100g", 3.12, "spinach, baby spinach, greens"),
    ("Garlic (3 pack)", "Produce", "Generic", 3.0, "unit", "unit", 3.0, "garlic, fresh garlic, garlic cloves"),
    ("Canned Crushed Tomatoes", "Pantry", "Unico", 796.0, "ml", "volume_100ml", 7.96, "canned tomatoes, crushed tomatoes, diced tomatoes, tomato sauce"),
    ("Garam Masala", "Pantry", "Suraj", 100.0, "g", "weight_100g", 1.0, "garam masala, curry powder, indian spices"),
    ("Long Grain Basmati Rice", "Pantry", "Tilda / Royal", 4.54, "kg", "weight_100g", 45.4, "basmati rice, rice, white rice"),
    ("Pasta Sauce (Marinara)", "Pantry", "Classico", 650.0, "ml", "volume_100ml", 6.5, "pasta sauce, marinara, spaghetti sauce"),
    ("Dry Spaghetti", "Pantry", "Barilla", 900.0, "g", "weight_100g", 9.0, "spaghetti, pasta, noodles"),
    ("White Sliced Sandwich Bread", "Bakery", "Wonder / D'Italiano", 675.0, "g", "weight_100g", 6.75, "bread, sliced bread, sandwich bread"),
    ("Extra Virgin Olive Oil", "Pantry", "Bertolli", 1.0, "L", "volume_100ml", 10.0, "olive oil, evoo, cooking oil"),
]

EVERYDAY: List[CatalogRow] = [
    # Dairy and eggs
    _item("Homogenized Milk 3.25%", "Dairy", 4, "L", "homo milk, whole milk, 3.25% milk, homogenized milk"),
    _item("1% Partly Skimmed Milk", "Dairy", 4, "L", "1% milk, one percent milk"),
    _item("Skim Milk", "Dairy", 4, "L", "skim milk, 0% milk, fat free milk"),
    _item("Chocolate Milk", "Dairy", 2, "L", "chocolate milk, choc milk"),
    _item("Unsweetened Almond Beverage", "Dairy", 1.89, "L", "almond milk, almond beverage"),
    _item("Oat Beverage", "Dairy", 1.75, "L", "oat milk, oat beverage"),
    _item("Soy Beverage", "Dairy", 1.89, "L", "soy milk, soy beverage"),
    _item("Coffee Cream 10%", "Dairy", 1, "L", "coffee cream, half and half, 10% cream, table cream"),
    _item("Large Grade A White Eggs (18-pack)", "Dairy", 18, "unit", "18 eggs, eggs 18"),
    _item("Unsalted Butter", "Dairy", 454, "g", "unsalted butter"),
    _item("Margarine", "Dairy", 850, "g", "margarine, soft margarine, becel"),
    _item("Mozzarella Cheese Block", "Dairy", 400, "g", "mozzarella, mozzarella cheese, mozza"),
    _item("Shredded Cheese Blend", "Dairy", 320, "g", "shredded cheese, grated cheese, tex mex cheese, pizza mozzarella"),
    _item("Cheese Slices", "Dairy", 410, "g", "cheese slices, processed cheese slices, cheese singles, singles"),
    _item("Grated Parmesan Cheese", "Dairy", 250, "g", "parmesan, parmesan cheese, parmigiano"),
    _item("Feta Cheese", "Dairy", 200, "g", "feta, feta cheese"),
    _item("Cream Cheese", "Dairy", 250, "g", "cream cheese, philadelphia"),
    _item("Cottage Cheese", "Dairy", 500, "g", "cottage cheese"),
    _item("Sour Cream", "Dairy", 500, "ml", "sour cream"),
    _item("Vanilla Yogurt", "Dairy", 650, "g", "vanilla yogurt, flavoured yogurt"),
    _item("Yogurt Tubes (16 pack)", "Dairy", 16, "unit", "yogurt tubes, tubes, go gurt"),

    # Meat and seafood
    _item("Medium Ground Beef", "Meat", 1, "kg", "medium ground beef, regular ground beef"),
    _item("Ground Pork", "Meat", 1, "kg", "ground pork, minced pork"),
    _item("Ground Turkey", "Meat", 454, "g", "ground turkey"),
    _item("Pork Loin Chops", "Meat", 1, "kg", "pork chops, pork chop, pork loin chops"),
    _item("Whole Chicken", "Meat", 1, "kg", "whole chicken, roasting chicken, whole fryer"),
    _item("Chicken Drumsticks", "Meat", 1, "kg", "drumsticks, chicken drumsticks, chicken legs"),
    _item("Chicken Wings", "Meat", 1, "kg", "chicken wings, wings"),
    _item("Stewing Beef", "Meat", 1, "kg", "stewing beef, stew beef, beef cubes"),
    _item("Sirloin Steak", "Meat", 1, "kg", "sirloin, sirloin steak, steak"),
    _item("Bacon", "Meat", 375, "g", "bacon, sliced bacon, side bacon"),
    _item("Breakfast Sausages", "Meat", 375, "g", "breakfast sausage, sausages, sausage links"),
    _item("Wieners", "Meat", 450, "g", "wieners, hot dogs, franks"),
    _item("Sliced Deli Ham", "Meat", 175, "g", "ham, deli ham, sliced ham, black forest ham"),
    _item("Sliced Deli Turkey", "Meat", 175, "g", "deli turkey, sliced turkey, turkey breast slices"),
    _item("Frozen Raw Shrimp", "Seafood", 340, "g", "shrimp, prawns, frozen shrimp"),
    _item("Frozen Tilapia Fillets", "Seafood", 454, "g", "tilapia, white fish, frozen fish fillets"),
    _item("Canned Tuna", "Seafood", 170, "g", "tuna, canned tuna, flaked tuna, chunk tuna"),
    _item("Canned Salmon", "Seafood", 213, "g", "canned salmon, pink salmon"),

    # Produce
    _item("Gala Apples", "Produce", 1, "kg", "apples, apple, gala apples, gala"),
    _item("Navel Oranges", "Produce", 1, "kg", "oranges, orange, navel oranges"),
    _item("Mandarins (2 lb bag)", "Produce", 0.907, "kg", "mandarins, clementines, mandarin oranges, cuties"),
    _item("Lemon", "Produce", 1, "unit", "lemon, lemons"),
    _item("Lime", "Produce", 1, "unit", "lime, limes"),
    _item("Pears", "Produce", 1, "kg", "pears, pear, bartlett pears"),
    _item("Grapes", "Produce", 1, "kg", "grapes, red grapes, green grapes, seedless grapes"),
    _item("Strawberries (1 lb)", "Produce", 454, "g", "strawberries, strawberry"),
    _item("Blueberries (1 pint)", "Produce", 1, "unit", "blueberries, blueberry"),
    _item("Raspberries", "Produce", 170, "g", "raspberries, raspberry"),
    _item("Watermelon", "Produce", 1, "unit", "watermelon"),
    _item("Cantaloupe", "Produce", 1, "unit", "cantaloupe, melon"),
    _item("Russet Potatoes (10 lb bag)", "Produce", 4.54, "kg", "potatoes, potato, russet potatoes"),
    _item("Sweet Potatoes", "Produce", 1, "kg", "sweet potatoes, sweet potato, yams"),
    _item("Carrots (2 lb bag)", "Produce", 0.907, "kg", "carrots, carrot"),
    _item("Celery", "Produce", 1, "unit", "celery, celery stalks"),
    _item("Broccoli Crowns", "Produce", 1, "kg", "broccoli, broccoli crowns"),
    _item("Cauliflower", "Produce", 1, "unit", "cauliflower"),
    _item("Romaine Hearts (3 pack)", "Produce", 3, "unit", "romaine, romaine lettuce, romaine hearts"),
    _item("Iceberg Lettuce", "Produce", 1, "unit", "iceberg lettuce, lettuce, head lettuce"),
    _item("Spring Mix Salad", "Produce", 142, "g", "spring mix, salad mix, mixed greens, salad"),
    _item("English Cucumber", "Produce", 1, "unit", "cucumber, english cucumber, cukes"),
    _item("Tomatoes on the Vine", "Produce", 1, "kg", "tomatoes, tomato, vine tomatoes, tov"),
    _item("Red Bell Pepper", "Produce", 1, "unit", "red pepper, bell pepper, peppers, red bell pepper"),
    _item("Green Onions", "Produce", 1, "unit", "green onions, scallions, green onion"),
    _item("White Mushrooms", "Produce", 227, "g", "mushrooms, white mushrooms, button mushrooms"),
    _item("Zucchini", "Produce", 1, "kg", "zucchini, zucchinis"),
    _item("Ginger Root", "Produce", 1, "kg", "ginger, ginger root"),
    _item("Cilantro", "Produce", 1, "unit", "cilantro, coriander"),

    # Frozen
    _item("Frozen Mixed Vegetables", "Frozen", 750, "g", "frozen vegetables, mixed vegetables, frozen veggies"),
    _item("Frozen Peas", "Frozen", 750, "g", "frozen peas, peas, green peas"),
    _item("Frozen Mixed Berries", "Frozen", 600, "g", "frozen berries, frozen fruit, mixed berries"),
    _item("Frozen French Fries", "Frozen", 1, "kg", "french fries, fries, frozen fries"),
    _item("Frozen Pizza", "Frozen", 1, "unit", "frozen pizza, pizza"),
    _item("Ice Cream", "Frozen", 1.5, "L", "ice cream, vanilla ice cream"),

    # Bakery
    _item("Whole Wheat Sliced Bread", "Bakery", 675, "g", "whole wheat bread, brown bread, wheat bread"),
    _item("Hamburger Buns (8 pack)", "Bakery", 8, "unit", "hamburger buns, burger buns, buns"),
    _item("Hot Dog Buns (8 pack)", "Bakery", 8, "unit", "hot dog buns, wiener buns"),
    _item("Bagels (6 pack)", "Bakery", 6, "unit", "bagels, bagel"),
    _item("English Muffins (6 pack)", "Bakery", 6, "unit", "english muffins"),
    _item("Flour Tortillas (10 pack)", "Bakery", 10, "unit", "tortillas, wraps, flour tortillas"),

    # Pantry
    _item("All-Purpose Flour", "Pantry", 2.5, "kg", "flour, all purpose flour, white flour"),
    _item("Granulated White Sugar", "Pantry", 2, "kg", "sugar, white sugar, granulated sugar"),
    _item("Brown Sugar", "Pantry", 1, "kg", "brown sugar, golden yellow sugar"),
    _item("Canola Oil", "Pantry", 3, "L", "canola oil, vegetable oil, cooking oil canola"),
    _item("Jasmine Rice", "Pantry", 3.6, "kg", "jasmine rice"),
    _item("Penne Pasta", "Pantry", 900, "g", "penne, penne rigate, short pasta"),
    _item("Macaroni and Cheese Dinner", "Pantry", 200, "g", "kraft dinner, kd, mac and cheese, macaroni and cheese"),
    _item("Instant Noodles (5 pack)", "Pantry", 5, "unit", "instant noodles, ramen, mr noodles"),
    _item("Quick Oats", "Pantry", 1, "kg", "oats, oatmeal, quick oats, rolled oats"),
    _item("Toasted Oat Cereal", "Pantry", 400, "g", "cheerios, oat cereal, toasted oat cereal, cereal"),
    _item("Corn Flakes", "Pantry", 680, "g", "corn flakes, cornflakes"),
    _item("Peanut Butter", "Pantry", 1, "kg", "peanut butter, pb, smooth peanut butter"),
    _item("Strawberry Jam", "Pantry", 500, "ml", "jam, strawberry jam"),
    _item("Liquid Honey", "Pantry", 500, "g", "honey, liquid honey"),
    _item("Maple Syrup", "Pantry", 540, "ml", "maple syrup, syrup"),
    _item("Ketchup", "Pantry", 1, "L", "ketchup"),
    _item("Yellow Mustard", "Pantry", 400, "ml", "mustard, yellow mustard"),
    _item("Mayonnaise", "Pantry", 890, "ml", "mayo, mayonnaise"),
    _item("Salsa", "Pantry", 650, "ml", "salsa, chunky salsa"),
    _item("Soy Sauce", "Pantry", 500, "ml", "soy sauce"),
    _item("Chicken Broth", "Pantry", 900, "ml", "chicken broth, chicken stock"),
    _item("Beef Broth", "Pantry", 900, "ml", "beef broth, beef stock"),
    _item("Canned Black Beans", "Pantry", 540, "ml", "black beans"),
    _item("Canned Chickpeas", "Pantry", 540, "ml", "chickpeas, garbanzo beans"),
    _item("Canned Red Kidney Beans", "Pantry", 540, "ml", "kidney beans, red kidney beans"),
    _item("Baked Beans", "Pantry", 398, "ml", "baked beans, beans in molasses"),
    _item("Canned Corn", "Pantry", 341, "ml", "canned corn, corn niblets, kernel corn"),
    _item("Tomato Paste", "Pantry", 156, "ml", "tomato paste"),
    _item("Tomato Soup", "Pantry", 284, "ml", "tomato soup"),
    _item("Chicken Noodle Soup", "Pantry", 284, "ml", "chicken noodle soup"),
    _item("Ground Coffee", "Pantry", 920, "g", "coffee, ground coffee"),
    _item("Orange Pekoe Tea (72 bags)", "Pantry", 72, "unit", "tea, tea bags, orange pekoe, black tea"),
    _item("Table Salt", "Pantry", 1, "kg", "salt, table salt"),
    _item("Ground Black Pepper", "Pantry", 100, "g", "pepper, black pepper, ground pepper"),
    _item("Baking Soda", "Pantry", 500, "g", "baking soda"),
    _item("Chocolate Chips", "Pantry", 300, "g", "chocolate chips, chocolate chipits"),
    _item("Crackers", "Snacks", 200, "g", "crackers, ritz, soda crackers"),
    _item("Potato Chips", "Snacks", 235, "g", "chips, potato chips"),
    _item("Tortilla Chips", "Snacks", 300, "g", "tortilla chips, nachos, corn chips"),
    _item("Granola Bars (6 pack)", "Snacks", 6, "unit", "granola bars, granola bar"),

    # Drinks
    _item("Orange Juice", "Drinks", 1.54, "L", "orange juice, oj"),
    _item("Apple Juice", "Drinks", 1.89, "L", "apple juice"),
    _item("Bottled Water (24 x 500 ml)", "Drinks", 12, "L", "water, bottled water, spring water"),
    _item("Soft Drinks (12 x 355 ml)", "Drinks", 4.26, "L", "pop, soda, cola, soft drinks"),

    # Household
    _item("Paper Towels (6 rolls)", "Household", 6, "unit", "paper towels, paper towel"),
    _item("Toilet Paper (12 double rolls)", "Household", 12, "unit", "toilet paper, bathroom tissue, tp"),
    _item("Dish Soap", "Household", 709, "ml", "dish soap, dishwashing liquid"),
    _item("Laundry Detergent", "Household", 2.03, "L", "laundry detergent, detergent"),
    _item("Garbage Bags (40 pack)", "Household", 40, "unit", "garbage bags, trash bags"),
]

PRODUCT_CATALOG: List[CatalogRow] = STAPLES + EVERYDAY
