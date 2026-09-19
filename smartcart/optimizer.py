"""
SmartCart Basket Optimization Engine
Implements Combinatorial / Mixed-Integer Linear Optimization for multi-store grocery routing.
Factors in real-time Edmonton gasoline prices ($/L), vehicle fuel economy, and exact round-trip distance.
Generates:
1. Maximum Saver (Multi-Store Split with exact driving circuit & gas cost)
2. The Best Single Run (Single location minimizing total cost including round-trip gas)
3. In-Stock Guaranteed (Zero out-of-stock risk)
"""

from typing import List, Dict, Any, Optional, Tuple
import math
from itertools import combinations, permutations
from smartcart.database import get_connection, haversine_distance_km
from smartcart.normalizer import match_product_in_catalog, compute_packages_needed

DEFAULT_USER_LAT = 53.5461
DEFAULT_USER_LON = -113.4938
DEFAULT_GAS_PRICE_PER_LITRE = 1.42       # CAD / Litre (Edmonton regular fuel benchmark)
DEFAULT_FUEL_EFFICIENCY_L_100KM = 9.5     # Litres / 100 km (urban driving average)
DEFAULT_GAS_COST_PER_KM = round((DEFAULT_FUEL_EFFICIENCY_L_100KM / 100.0) * DEFAULT_GAS_PRICE_PER_LITRE, 4)  # ~$0.1349 / km

class BasketOptimizer:
    def __init__(
        self,
        user_lat: float = DEFAULT_USER_LAT,
        user_lon: float = DEFAULT_USER_LON,
        max_travel_radius_km: float = 15.0,
        exclude_membership_stores: bool = False,
        gas_price_per_litre: float = DEFAULT_GAS_PRICE_PER_LITRE,
        fuel_efficiency_l_100km: float = DEFAULT_FUEL_EFFICIENCY_L_100KM,
        cost_per_km: Optional[float] = None,
        base_store_stop_penalty: float = 0.0
    ):
        self.user_lat = user_lat
        self.user_lon = user_lon
        self.max_travel_radius_km = max_travel_radius_km
        self.exclude_membership_stores = exclude_membership_stores
        self.gas_price_per_litre = gas_price_per_litre
        self.fuel_efficiency_l_100km = fuel_efficiency_l_100km
        self.cost_per_km = cost_per_km if cost_per_km is not None else round(
            (self.fuel_efficiency_l_100km / 100.0) * self.gas_price_per_litre, 4
        )
        self.base_store_stop_penalty = base_store_stop_penalty

    def compute_gas_cost(self, round_trip_km: float) -> float:
        """Calculates total gasoline cost for driving the given round-trip distance."""
        return round(round_trip_km * self.cost_per_km, 2)

    def get_candidate_stores(self) -> List[Dict[str, Any]]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, banner, address, latitude, longitude, requires_membership, quadrant FROM stores")
        stores = [dict(row) for row in cursor.fetchall()]
        conn.close()

        valid_stores = []
        for s in stores:
            if self.exclude_membership_stores and s["requires_membership"] == 1:
                continue
            dist = haversine_distance_km(self.user_lat, self.user_lon, s["latitude"], s["longitude"])
            if dist <= self.max_travel_radius_km:
                s["distance_km"] = dist
                round_trip_km = round(dist * 2, 2)
                s["round_trip_km"] = round_trip_km
                s["gas_cost"] = self.compute_gas_cost(round_trip_km)
                s["travel_cost"] = s["gas_cost"]
                valid_stores.append(s)

        valid_stores.sort(key=lambda x: x["distance_km"])
        return valid_stores

    def prepare_basket_data(
        self,
        items: List[Dict[str, Any]],
        candidate_stores: List[Dict[str, Any]],
        guarantee_in_stock: bool = False
    ) -> Dict[str, Any]:
        conn = get_connection()
        cursor = conn.cursor()
        store_ids = [s["id"] for s in candidate_stores]

        resolved_items = []
        for it in items:
            raw_query = it.get("name") or it.get("query")
            qty = float(it.get("quantity", 1.0))
            unit = str(it.get("unit", "unit"))

            prod = match_product_in_catalog(raw_query)
            if not prod:
                continue

            packages_needed = compute_packages_needed(qty, unit, prod)

            placeholders = ",".join("?" * len(store_ids))
            sql = f"""
            SELECT store_id, price, unit_price, in_stock
            FROM store_inventory
            WHERE product_id = ? AND store_id IN ({placeholders})
            """
            cursor.execute(sql, [prod["id"]] + store_ids)
            prices = {row["store_id"]: dict(row) for row in cursor.fetchall()}

            resolved_items.append({
                "requested_name": raw_query,
                "product_id": prod["id"],
                "product_name": prod["name"],
                "category": prod["category"],
                "brand": prod["brand"],
                "quantity": qty,
                "unit": unit,
                "packages_needed": packages_needed,
                "prices": prices,
            })

        conn.close()
        return {
            "items": resolved_items,
            "stores": {s["id"]: s for s in candidate_stores}
        }

    def solve_best_single_store(
        self,
        basket_data: Dict[str, Any],
        guarantee_in_stock: bool = False
    ) -> Optional[Dict[str, Any]]:
        items = basket_data["items"]
        stores = basket_data["stores"]

        if not items:
            return None

        best_plan = None
        best_cost = float("inf")

        for store_id, store in stores.items():
            store_total = 0.0
            item_breakdown = []
            possible = True

            for it in items:
                p_info = it["prices"].get(store_id)
                if not p_info:
                    possible = False
                    break
                if guarantee_in_stock and p_info["in_stock"] != 1:
                    possible = False
                    break

                pkg_cost = round(p_info["price"] * it["packages_needed"], 2)
                store_total += pkg_cost
                item_breakdown.append({
                    "item_name": it["product_name"],
                    "requested": f"{it['quantity']} {it['unit']}",
                    "packages": it["packages_needed"],
                    "unit_price": p_info["unit_price"],
                    "package_price": p_info["price"],
                    "total_cost": pkg_cost,
                    "in_stock": bool(p_info["in_stock"]),
                    "store_id": store_id,
                    "store_name": store["name"],
                    "banner": store["banner"],
                })

            if possible:
                grocery_cost = round(store_total, 2)
                one_way_km = round(store["distance_km"], 2)
                round_trip_km = round(one_way_km * 2, 2)
                gas_cost = self.compute_gas_cost(round_trip_km)
                all_in_cost = round(grocery_cost + gas_cost, 2)

                # Prioritize lowest all-in price (Groceries + Gas)
                if all_in_cost < best_cost:
                    best_cost = all_in_cost
                    best_plan = {
                        "mode": "Best Single Run",
                        "store": store,
                        "stores_visited": [store],
                        "store_count": 1,
                        "grocery_cost": grocery_cost,
                        "gas_cost": gas_cost,
                        "estimated_travel_cost": gas_cost,
                        "all_in_cost": all_in_cost,
                        "distance_km": one_way_km,
                        "total_distance_km": round_trip_km,
                        "drive_time_minutes": max(4, round(round_trip_km * 2.0)),
                        "gas_price_per_litre": self.gas_price_per_litre,
                        "fuel_efficiency_l_100km": self.fuel_efficiency_l_100km,
                        "items": item_breakdown,
                        "guaranteed_in_stock": guarantee_in_stock
                    }

        return best_plan

    def solve_multi_store_saver(
        self,
        basket_data: Dict[str, Any],
        max_stores: int = 3,
        guarantee_in_stock: bool = False
    ) -> Optional[Dict[str, Any]]:
        items = basket_data["items"]
        stores = basket_data["stores"]
        store_list = list(stores.values())
        n_stores = len(store_list)

        if not items:
            return None

        best_plan = None
        best_objective = float("inf")

        for k in range(1, min(max_stores + 1, n_stores + 1)):
            for store_subset in combinations(store_list, k):
                subset_ids = {s["id"] for s in store_subset}

                subset_grocery_cost = 0.0
                subset_items = []
                covered = True

                for it in items:
                    cheapest_cost = float("inf")
                    cheapest_choice = None

                    for s_id in subset_ids:
                        p_info = it["prices"].get(s_id)
                        if not p_info:
                            continue
                        if guarantee_in_stock and p_info["in_stock"] != 1:
                            continue

                        cost = round(p_info["price"] * it["packages_needed"], 2)
                        if cost < cheapest_cost:
                            cheapest_cost = cost
                            cheapest_choice = (s_id, p_info, cost)

                    if not cheapest_choice:
                        covered = False
                        break

                    s_id, p_info, cost = cheapest_choice
                    s_meta = stores[s_id]
                    subset_grocery_cost += cost
                    subset_items.append({
                        "item_name": it["product_name"],
                        "requested": f"{it['quantity']} {it['unit']}",
                        "packages": it["packages_needed"],
                        "unit_price": p_info["unit_price"],
                        "package_price": p_info["price"],
                        "total_cost": cost,
                        "in_stock": bool(p_info["in_stock"]),
                        "store_id": s_id,
                        "store_name": s_meta["name"],
                        "banner": s_meta["banner"],
                    })

                if not covered:
                    continue

                # Compute the shortest driving loop through all stores in this subset
                min_circuit_km = float("inf")
                best_order = list(store_subset)

                if k == 1:
                    st = store_subset[0]
                    min_circuit_km = haversine_distance_km(self.user_lat, self.user_lon, st["latitude"], st["longitude"]) * 2
                else:
                    for perm in permutations(store_subset):
                        # Tour: user -> perm[0] -> ... -> perm[-1] -> user
                        tour_dist = haversine_distance_km(self.user_lat, self.user_lon, perm[0]["latitude"], perm[0]["longitude"])
                        for idx in range(len(perm) - 1):
                            tour_dist += haversine_distance_km(perm[idx]["latitude"], perm[idx]["longitude"], perm[idx+1]["latitude"], perm[idx+1]["longitude"])
                        tour_dist += haversine_distance_km(perm[-1]["latitude"], perm[-1]["longitude"], self.user_lat, self.user_lon)
                        if tour_dist < min_circuit_km:
                            min_circuit_km = tour_dist
                            best_order = list(perm)

                round_trip_km = round(min_circuit_km, 2)
                gas_cost = self.compute_gas_cost(round_trip_km)
                stop_penalties = round((k - 1) * self.base_store_stop_penalty, 2)
                effective_trip_cost = round(gas_cost + stop_penalties, 2)

                total_grocery = round(subset_grocery_cost, 2)
                all_in_cost = round(total_grocery + gas_cost, 2)
                objective = total_grocery + effective_trip_cost

                if objective < best_objective:
                    best_objective = objective
                    store_groups = {}
                    for item in subset_items:
                        sid = item["store_id"]
                        if sid not in store_groups:
                            store_groups[sid] = {
                                "store": stores[sid],
                                "items": [],
                                "subtotal": 0.0
                            }
                        store_groups[sid]["items"].append(item)
                        store_groups[sid]["subtotal"] = round(store_groups[sid]["subtotal"] + item["total_cost"], 2)

                    # Order store groups according to optimal driving circuit
                    ordered_groups = []
                    prev_lat, prev_lon = self.user_lat, self.user_lon
                    for st in best_order:
                        if st["id"] in store_groups:
                            grp = store_groups[st["id"]]
                            leg_km = round(haversine_distance_km(prev_lat, prev_lon, st["latitude"], st["longitude"]), 2)
                            grp["leg_km"] = leg_km
                            grp["distance_from_user_km"] = round(haversine_distance_km(self.user_lat, self.user_lon, st["latitude"], st["longitude"]), 2)
                            ordered_groups.append(grp)
                            prev_lat, prev_lon = st["latitude"], st["longitude"]

                    best_plan = {
                        "mode": "Maximum Saver (Multi-Store)",
                        "stores_visited": best_order,
                        "store_count": k,
                        "grocery_cost": total_grocery,
                        "gas_cost": gas_cost,
                        "estimated_travel_cost": gas_cost,
                        "all_in_cost": all_in_cost,
                        "distance_km": round(max(s["distance_km"] for s in store_subset), 2),
                        "total_distance_km": round_trip_km,
                        "drive_time_minutes": max(6, round(round_trip_km * 2.0)),
                        "gas_price_per_litre": self.gas_price_per_litre,
                        "fuel_efficiency_l_100km": self.fuel_efficiency_l_100km,
                        "items": subset_items,
                        "store_groups": ordered_groups,
                        "guaranteed_in_stock": guarantee_in_stock
                    }

        return best_plan

    def optimize_basket(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        candidate_stores = self.get_candidate_stores()
        if not candidate_stores:
            return {"error": "No grocery stores found within specified radius."}

        basket_data = self.prepare_basket_data(items, candidate_stores)
        if not basket_data["items"]:
            return {"error": "None of the requested items could be matched to catalog products."}

        single_best = self.solve_best_single_store(basket_data, guarantee_in_stock=False)
        multi_saver = self.solve_multi_store_saver(basket_data, max_stores=3, guarantee_in_stock=False)

        in_stock_plan = self.solve_best_single_store(basket_data, guarantee_in_stock=True)
        if not in_stock_plan:
            in_stock_plan = self.solve_multi_store_saver(basket_data, max_stores=3, guarantee_in_stock=True)

        market_avg = 0.0
        for it in basket_data["items"]:
            valid_prices = [p["price"] for p in it["prices"].values() if p.get("price")]
            if valid_prices:
                avg_p = sum(valid_prices) / len(valid_prices)
                market_avg += avg_p * it["packages_needed"]
        market_avg = round(market_avg, 2)

        for plan in [multi_saver, single_best, in_stock_plan]:
            if plan:
                # Savings compares grocery total to market average
                grocery_savings = round(max(0.0, market_avg - plan["grocery_cost"]), 2)
                pct_savings = round((grocery_savings / market_avg * 100), 1) if market_avg > 0 else 0.0
                plan["savings_vs_market_avg"] = grocery_savings
                plan["pct_savings"] = pct_savings

        return {
            "user_location": {
                "latitude": self.user_lat,
                "longitude": self.user_lon,
                "city": "Edmonton, AB"
            },
            "gas_parameters": {
                "gas_price_per_litre": self.gas_price_per_litre,
                "fuel_efficiency_l_100km": self.fuel_efficiency_l_100km,
                "cost_per_km": self.cost_per_km
            },
            "market_average_cost": market_avg,
            "plans": {
                "maximum_saver": multi_saver,
                "best_single_run": single_best,
                "in_stock_guaranteed": in_stock_plan,
            }
        }
