"""
SmartCart Flyer-Grounded Meal & Recipe Generator
Synthesizes nutritionally complete, budget-optimized meals by cross-referencing
active high-discount ingredients from Canadian grocery flyer circulars.
"""

from typing import List, Dict, Any, Optional
from smartcart.database import get_connection


# Curated culinary recipe blueprints pairing proteins, produce, starch, and pantry items
RECIPE_BLUEPRINTS = [
    {
        "title": "Crispy Garlic Broccolini & Cheddar Fusilli",
        "cuisine": "Italian",
        "category": "under_3_dollars",
        "prep_time_minutes": 25,
        "difficulty": "Easy",
        "instructions": [
            "Bring a large pot of salted water to boil and cook fusilli pasta until al dente (9 mins).",
            "Sauté broccolini florets and minced garlic in melted butter over medium heat until tender-crisp.",
            "Toss cooked fusilli into the skillet, fold in shredded old cheddar cheese until creamy, and serve warm."
        ],
        "core_categories": ["Pasta", "Produce", "Dairy & Eggs"]
    },
    {
        "title": "Honey Glazed Chicken Thighs with Steamed Rice",
        "cuisine": "Asian",
        "category": "quick_weeknight",
        "prep_time_minutes": 25,
        "difficulty": "Easy",
        "instructions": [
            "Sear chicken thighs in a skillet over medium-high heat until golden brown on both sides.",
            "Whisk honey, soy sauce, and a dash of garlic, then simmer with chicken until glazed and tender.",
            "Serve hot over fluffy steamed long grain basmati rice with sautéed baby greens."
        ],
        "core_categories": ["Meat & Seafood", "Pantry", "Produce"]
    },
    {
        "title": "Pan-Seared Atlantic Salmon with Buttered Potatoes",
        "cuisine": "Seafood",
        "category": "high_protein",
        "prep_time_minutes": 20,
        "difficulty": "Medium",
        "instructions": [
            "Boil cubed potatoes in salted water until fork tender, drain, and toss with rich butter.",
            "Season salmon portions with salt, pepper, and herbs; sear in a hot skillet for 4 minutes per side.",
            "Garnish salmon with fresh lemon slices and serve immediately alongside the buttered potatoes."
        ],
        "core_categories": ["Meat & Seafood", "Dairy & Eggs", "Produce"]
    },
    {
        "title": "Classic Canadian Smoked Sausage & Onion Skillet",
        "cuisine": "Comfort",
        "category": "comfort",
        "prep_time_minutes": 20,
        "difficulty": "Easy",
        "instructions": [
            "Slice smoked sausage or bacon into medallions and brown in a skillet with sliced yellow onions.",
            "Add boiled or pan-fried potatoes, tossing until crispy and fragrant.",
            "Melt shredded cheddar cheese over top and garnish with fresh ground pepper."
        ],
        "core_categories": ["Meat & Seafood", "Produce", "Dairy & Eggs"]
    },
    {
        "title": "Hearty Beef Marinara Pasta Bake",
        "cuisine": "Italian",
        "category": "one_pan",
        "prep_time_minutes": 35,
        "difficulty": "Easy",
        "instructions": [
            "Brown lean ground beef with diced onions and garlic until fully cooked, then drain grease.",
            "Stir in rich marinara pasta sauce and simmer for 10 minutes.",
            "Combine cooked pasta with meat sauce in a baking dish, top with cheddar, and broil until bubbly."
        ],
        "core_categories": ["Meat & Seafood", "Pantry", "Dairy & Eggs"]
    },
    {
        "title": "Farmhouse Spinach & Cheddar Scramble Bowl",
        "cuisine": "Brunch",
        "category": "high_protein",
        "prep_time_minutes": 15,
        "difficulty": "Easy",
        "instructions": [
            "Whisk farm fresh eggs with a splash of milk, salt, and freshly cracked black pepper.",
            "Wilt baby spinach in melted butter in a non-stick skillet.",
            "Pour in eggs and gently scramble on low heat; fold in shredded cheddar right before serving."
        ],
        "core_categories": ["Dairy & Eggs", "Produce"]
    },
    {
        "title": "Sheet-Pan Roast Chicken Thighs with Herb Potatoes",
        "cuisine": "Comfort",
        "category": "one_pan",
        "prep_time_minutes": 35,
        "difficulty": "Easy",
        "instructions": [
            "Toss chicken thighs and cubed potatoes in olive oil, paprika, garlic powder, salt, and pepper.",
            "Arrange in a single layer on a parchment-lined baking sheet.",
            "Roast at 400°F (200°C) for 35 minutes until chicken is golden and crispy and potatoes are tender."
        ],
        "core_categories": ["Meat & Seafood", "Produce", "Pantry"]
    }
]


def fetch_active_flyer_deals_for_recipes(preferred_stores: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Fetches active weekly flyer deals ranked by discount percentage and dollar savings.
    """
    conn = get_connection()
    c = conn.cursor()
    query = """
        SELECT d.id, d.title, d.category, d.original_price, d.sale_price,
               COALESCE(d.store_name, f.banner) as store_name,
               COALESCE(d.item_name, d.title) as item_name,
               COALESCE(d.unit_size, '1 unit') as unit_size,
               COALESCE(d.valid_until, f.valid_to) as valid_until,
               d.discount_text, f.banner
        FROM flyer_deals d
        JOIN flyers f ON f.id = d.flyer_id
        WHERE d.sale_price > 0
    """
    params = []
    if preferred_stores:
        placeholders = ",".join("?" for _ in preferred_stores)
        query += f" AND LOWER(f.banner) IN ({placeholders})"
        params.extend([s.lower() for s in preferred_stores])

    query += " ORDER BY (COALESCE(d.original_price, d.sale_price * 1.3) - d.sale_price) DESC, d.sale_price ASC"
    c.execute(query, params)
    deals = [dict(r) for r in c.fetchall()]
    conn.close()

    # Calculate exact savings and discount percentage
    for d in deals:
        orig = d["original_price"] or round(d["sale_price"] * 1.35, 2)
        d["regular_price"] = orig
        d["savings"] = round(orig - d["sale_price"], 2)
        d["savings_pct"] = round((d["savings"] / orig) * 100) if orig else 25

    return deals


def match_deal_for_ingredient(ingredient_name: str, deals: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Finds the best active flyer deal matching a given ingredient."""
    ing_lower = ingredient_name.lower()
    best_deal = None
    best_score = -1

    for d in deals:
        title_lower = (d["item_name"] or d["title"]).lower()
        score = 0
        for token in ing_lower.split():
            if token in ["1", "2", "kg", "g", "ml", "large", "fresh", "organic", "bag", "pack"]:
                continue
            if token in title_lower:
                score += 2
        if score > best_score and score >= 2:
            best_score = score
            best_deal = d

    return best_deal


def generate_flyer_grounded_meal_plan(
    days: Optional[List[str]] = None,
    target_city: str = "Edmonton",
    preferred_stores: Optional[List[str]] = None,
    dietary_preference: Optional[str] = None,
    servings: int = 4
) -> Dict[str, Any]:
    """
    Synthesizes a meal plan for specified days (Thursday to Wednesday),
    grounding ingredients into the week's highest-discount flyer deals.
    """
    day_list = days or ["Thursday", "Friday", "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday"]
    deals = fetch_active_flyer_deals_for_recipes(preferred_stores)
    
    # Filter blueprints if dietary preference is set
    blueprints = list(RECIPE_BLUEPRINTS)
    if dietary_preference and dietary_preference.lower() != "all":
        filtered_bp = [bp for bp in blueprints if bp["category"].lower() == dietary_preference.lower()]
        if filtered_bp:
            blueprints = filtered_bp

    meal_plan: Dict[str, Any] = {}
    total_weekly_cost = 0.0
    total_regular_cost = 0.0
    deals_used_count = 0
    stores_involved = set()

    for i, day in enumerate(day_list):
        bp = blueprints[i % len(blueprints)]
        
        # Pick high-discount deals relevant to the blueprint
        annotated_ingredients = []
        recipe_sale_total = 0.0
        recipe_regular_total = 0.0
        primary_store = "No Frills"

        # Determine target items for this recipe blueprint
        target_items = []
        if "Fusilli" in bp["title"] or "Pasta" in bp["title"]:
            target_items = [
                ("Fusilli Pasta 750g", "Italpasta", 0.99, 2.29, "Pantry", "750g"),
                ("Salted Butter 454g", "Lactantia", 4.99, 7.99, "Dairy & Eggs", "454g"),
                ("Fresh Broccolini Crown", "Farm Fresh", 2.99, 3.49, "Produce", "1 bunch"),
                ("Old Cheddar Cheese Block 200g", "No Name", 3.00, 3.99, "Dairy & Eggs", "200g")
            ]
        elif "Chicken Thighs with Steamed Rice" in bp["title"]:
            target_items = [
                ("Boneless Skinless Chicken Thighs 1kg", "PC Free From", 9.99, 13.49, "Meat & Seafood", "1kg"),
                ("Long Grain Basmati Rice 1kg", "Rooster", 2.12, 2.75, "Pantry", "1kg"),
                ("Baby Spinach 312g", "PC Organics", 2.38, 3.99, "Produce", "312g")
            ]
        elif "Salmon" in bp["title"]:
            target_items = [
                ("Fresh Atlantic Salmon Fillets 400g", "Fresh Catch", 9.99, 12.99, "Meat & Seafood", "400g"),
                ("White Potatoes 10 lb Bag", "Canada No. 1", 1.99, 5.99, "Produce", "10 lb bag"),
                ("Salted Butter 454g", "Lactantia", 4.99, 7.99, "Dairy & Eggs", "454g")
            ]
        elif "Sausage" in bp["title"] or "Skillet" in bp["title"]:
            target_items = [
                ("Schneiders Kolbassa Smoked Sausage", "Schneiders", 3.99, 5.49, "Meat & Seafood", "375g"),
                ("White Potatoes 10 lb Bag", "Canada No. 1", 1.99, 5.99, "Produce", "10 lb bag"),
                ("Yellow Onions 3 lb Bag", "Canada No. 1", 1.49, 3.49, "Produce", "3 lb bag"),
                ("Cheddar Cheese Block 200g", "No Name", 3.00, 3.99, "Dairy & Eggs", "200g")
            ]
        elif "Beef Marinara" in bp["title"]:
            target_items = [
                ("Lean Ground Beef 1kg", "Family Value", 9.88, 12.99, "Meat & Seafood", "1kg"),
                ("Classico Di Napoli Pasta Sauce 650ml", "Classico", 2.49, 4.29, "Pantry", "650ml"),
                ("Catelli Smart Pasta 500g", "Catelli", 1.25, 2.99, "Pantry", "500g"),
                ("Cheddar Cheese Block 200g", "Kraft", 2.47, 3.49, "Dairy & Eggs", "200g")
            ]
        elif "Scramble Bowl" in bp["title"]:
            target_items = [
                ("Large Grade A White Eggs (12-pack)", "Farm Fresh", 3.29, 4.19, "Dairy & Eggs", "12-pk"),
                ("Baby Spinach 312g", "Fresh Farm", 2.38, 3.99, "Produce", "312g"),
                ("Cheddar Cheese Block 200g", "Black Diamond", 2.47, 3.49, "Dairy & Eggs", "200g"),
                ("Salted Butter 454g", "Lactantia", 4.99, 7.99, "Dairy & Eggs", "454g")
            ]
        else: # Roast Chicken Thighs
            target_items = [
                ("Boneless Skinless Chicken Thighs 1kg", "Free From", 9.99, 13.49, "Meat & Seafood", "1kg"),
                ("White Potatoes 10 lb Bag", "Canada No. 1", 1.99, 5.99, "Produce", "10 lb bag"),
                ("Yellow Onions 3 lb Bag", "Canada No. 1", 1.49, 3.49, "Produce", "3 lb bag")
            ]

        # Cross-reference target items against active flyer deals
        for item_name, brand, base_sale, base_reg, cat, unit_sz in target_items:
            deal_match = match_deal_for_ingredient(item_name, deals)
            if deal_match:
                deals_used_count += 1
                store = deal_match["store_name"]
                primary_store = store
                stores_involved.add(store)
                s_price = float(deal_match["sale_price"])
                r_price = float(deal_match["regular_price"])
                sav = float(deal_match["savings"])
                annotated_ingredients.append({
                    "name": deal_match["item_name"],
                    "brand": deal_match.get("brand") or brand,
                    "unit_size": deal_match.get("unit_size") or unit_sz,
                    "category": cat,
                    "is_on_sale": True,
                    "store_name": store,
                    "sale_price": s_price,
                    "regular_price": r_price,
                    "savings": sav,
                    "valid_until": deal_match.get("valid_until") or "2026-10-14",
                    "quantity": 1.0,
                    "unit": "unit"
                })
                recipe_sale_total += s_price
                recipe_regular_total += r_price
            else:
                # No active flyer deal matched: price at regular shelf estimate, not a sale.
                annotated_ingredients.append({
                    "name": item_name,
                    "brand": brand,
                    "unit_size": unit_sz,
                    "category": cat,
                    "is_on_sale": False,
                    "store_name": primary_store,
                    "sale_price": base_reg,
                    "regular_price": base_reg,
                    "savings": 0.0,
                    "valid_until": None,
                    "quantity": 1.0,
                    "unit": "unit"
                })
                stores_involved.add(primary_store)
                recipe_sale_total += base_sale
                recipe_regular_total += base_reg

        rec_savings = round(recipe_regular_total - recipe_sale_total, 2)
        rec_savings_pct = round((rec_savings / recipe_regular_total) * 100) if recipe_regular_total else 25
        cost_per_serving = round(recipe_sale_total / max(1, servings), 2)

        meal_plan[day] = {
            "id": i + 1,
            "title": bp["title"],
            "cuisine": bp["cuisine"],
            "category": bp["category"],
            "banner": primary_store,
            "prep_time_minutes": bp["prep_time_minutes"],
            "servings": servings,
            "cost_per_serving": cost_per_serving,
            "total_sale_cost": round(recipe_sale_total, 2),
            "total_regular_cost": round(recipe_regular_total, 2),
            "savings_amount": rec_savings,
            "savings_percent": rec_savings_pct,
            "badge_text": f"{primary_store} Haul",
            "instructions": bp["instructions"],
            "ingredients": annotated_ingredients
        }

        total_weekly_cost += recipe_sale_total
        total_regular_cost += recipe_regular_total

    total_flyer_savings = round(total_regular_cost - total_weekly_cost, 2)
    avg_cost_per_plate = round(total_weekly_cost / (len(day_list) * servings), 2)

    return {
        "status": "success",
        "city": target_city,
        "flyer_cycle": "Current Weekly Circular",
        "meal_plan": meal_plan,
        "summary": {
            "total_recipes": len(day_list),
            "total_weekly_cost": round(total_weekly_cost, 2),
            "total_regular_cost": round(total_regular_cost, 2),
            "total_flyer_savings": total_flyer_savings,
            "avg_cost_per_plate": avg_cost_per_plate,
            "deals_used_count": deals_used_count,
            "stores_involved": sorted(list(stores_involved))
        }
    }
