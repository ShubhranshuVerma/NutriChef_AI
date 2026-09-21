"""Deterministic nutrition and cost calculator.

Nutrition = sum over ingredients of (grams / 100) * nutrients_per_100g.
Numbers come only from the USDA-linked table - never from an LLM.

Usage:
    tables = load_tables()
    result = calculate_recipe(ingredients, tables, servings=2)
"""

import pandas as pd

from app.core.config import PROJECT_ROOT
from app.data.reference import load_prices
from app.nutrition.food_matcher import IngredientMatcher, load_catalog
from app.nutrition.parsing import parse_ingredient
from app.nutrition.units import to_grams

INGREDIENT_FOODS_PATH = PROJECT_ROOT / "data" / "processed" / "ingredient_foods.csv"
NUTRIENTS = ["kcal", "protein_g", "carbs_g", "fat_g", "fiber_g"]

# Typical calories per serving, used only to estimate servings when a recipe doesn't say.
KCAL_PER_SERVING = {"main": 500, "breakfast": 400, "side": 250, "snack": 250,
                    "dessert": 300, "beverage": 150}
MAX_SERVINGS = 12

# Small, cheap pantry items: no price needed.
PANTRY_CATEGORIES = ["spice", "herb"]


def load_tables():
    """Load everything the calculator needs into simple dictionaries."""
    catalog = load_catalog().set_index("ingredient_id")
    foods = pd.read_csv(INGREDIENT_FOODS_PATH).set_index("ingredient_id")
    foods[NUTRIENTS] = foods[NUTRIENTS].fillna(0)  # e.g. fibre not reported -> 0
    return {
        "catalog": catalog.to_dict("index"),
        "nutrients": foods[NUTRIENTS].to_dict("index"),
        "price_per_gram": price_per_gram_table(),
        "matcher": IngredientMatcher(),
    }


def price_per_gram_table():
    """Turn the price list (per kg / l / piece) into rupees per gram for each ingredient id."""
    matcher = IngredientMatcher()
    table = {}
    for row in load_prices().itertuples():
        ingredient_id = matcher.match(row.item)
        if ingredient_id is None:
            continue
        grams = 1000 if row.per_unit == "kg" else row.grams_per_unit
        table.setdefault(ingredient_id, row.price_inr / grams)
    return table


def ingredient_details(item, tables):
    """Grams, nutrients and cost for one parsed ingredient (a dict)."""
    ingredient_id = item.get("ingredient_id")
    result = {"name": item.get("name", ""), "ingredient_id": ingredient_id, "grams": None,
              "cost_inr": None, "status": "ok"}
    result.update(dict.fromkeys(NUTRIENTS, 0.0))

    if ingredient_id is None:
        result["status"] = "unknown_ingredient"
        return result

    info = tables["catalog"][ingredient_id]
    if item.get("quantity") is None:
        # "salt to taste" is fine; "some chicken" is not
        result["status"] = "to_taste" if info["category"] in PANTRY_CATEGORIES else "no_quantity"
        return result

    grams = to_grams(item["quantity"], item["unit"], ingredient_id,
                     info["density_g_ml"], info["grams_per_piece"])
    if grams is None:
        result["status"] = "unknown_amount"
        return result

    result["grams"] = round(grams, 1)
    per_100g = tables["nutrients"].get(ingredient_id)
    if per_100g is None:
        result["status"] = "no_nutrition_data"
    else:
        for n in NUTRIENTS:
            result[n] = grams / 100 * per_100g[n]

    price = tables["price_per_gram"].get(ingredient_id)
    if price is not None:
        result["cost_inr"] = grams * price
    elif info["category"] in PANTRY_CATEGORIES or info["nutrition_source"] == "negligible":
        result["cost_inr"] = 0.0
    return result


def estimate_servings(total_kcal, course):
    target = KCAL_PER_SERVING.get(course, 500)
    return int(min(MAX_SERVINGS, max(1, round(total_kcal / target))))


def calculate_recipe(ingredients, tables, servings=None, course="main"):
    """Totals and per-serving nutrition and cost for a list of parsed ingredients."""
    details = [ingredient_details(item, tables) for item in ingredients]

    totals = {n: sum(d[n] for d in details) for n in NUTRIENTS}
    total_grams = sum(d["grams"] or 0 for d in details)

    counted = [d for d in details if d["status"] != "to_taste"]
    ok = [d for d in counted if d["status"] == "ok"]
    coverage = len(ok) / len(counted) if counted else 0.0

    priced = [d for d in details if d["cost_inr"] is not None]
    total_cost = sum(d["cost_inr"] for d in priced)
    cost_coverage = len(priced) / len(details) if details else 0.0

    servings_estimated = servings is None
    if servings_estimated:
        servings = estimate_servings(totals["kcal"], course)

    per_serving = {n: totals[n] / servings for n in NUTRIENTS}

    return {
        "servings": servings,
        "servings_estimated": servings_estimated,
        "total_grams": round(total_grams),
        "total": _rounded(totals),
        "per_serving": _rounded(per_serving),
        "cost_inr_total": round(total_cost, 2),
        "cost_inr_per_serving": round(total_cost / servings, 2),
        "cost_coverage": round(cost_coverage, 2),
        "coverage": round(coverage, 2),
        "confidence": "high" if coverage >= 0.95 else "medium" if coverage >= 0.8 else "low",
        "problems": [f"{d['name']} ({d['status']})" for d in counted if d["status"] != "ok"],
        "ingredients": details,
    }


def calculate_from_text(lines, tables, servings=None, course="main"):
    """Convenience: ['200 g paneer', '1 onion'] -> nutrition result."""
    ingredients = []
    for line in lines:
        item = parse_ingredient(line)
        ingredients.append({"name": item.name, "quantity": item.quantity, "unit": item.unit,
                            "ingredient_id": tables["matcher"].match(item.name)})
    return calculate_recipe(ingredients, tables, servings, course)


def _rounded(values):
    return {n: round(v) if n == "kcal" else round(v, 1) for n, v in values.items()}
