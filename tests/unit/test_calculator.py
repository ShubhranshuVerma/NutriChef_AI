"""Calculator tests use small hand-made tables, so they don't need the USDA files."""

import pytest

from app.nutrition.calculator import calculate_recipe, estimate_servings, ingredient_details


@pytest.fixture
def tables():
    catalog = {
        "paneer": {"category": "dairy", "density_g_ml": 0.55, "grams_per_piece": 0,
                   "nutrition_source": "usda_proxy"},
        "egg": {"category": "egg", "density_g_ml": 1.03, "grams_per_piece": 50,
                "nutrition_source": "usda"},
        "oil": {"category": "oil_fat", "density_g_ml": 0.92, "grams_per_piece": 0,
                "nutrition_source": "usda"},
        "salt": {"category": "spice", "density_g_ml": 1.2, "grams_per_piece": 0,
                 "nutrition_source": "usda"},
        "water": {"category": "beverage", "density_g_ml": 1.0, "grams_per_piece": 0,
                  "nutrition_source": "negligible"},
    }
    nutrients = {
        "paneer": {"kcal": 300, "protein_g": 22, "carbs_g": 2, "fat_g": 22, "fiber_g": 0},
        "egg": {"kcal": 143, "protein_g": 12.6, "carbs_g": 0.7, "fat_g": 9.5, "fiber_g": 0},
        "oil": {"kcal": 884, "protein_g": 0, "carbs_g": 0, "fat_g": 100, "fiber_g": 0},
        "salt": {"kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0},
        "water": {"kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0},
    }
    prices = {"paneer": 0.4, "egg": 0.14, "oil": 0.163}  # rupees per gram
    return {"catalog": catalog, "nutrients": nutrients, "price_per_gram": prices,
            "matcher": None}


def item(ingredient_id, quantity, unit, name=None):
    return {"name": name or ingredient_id, "ingredient_id": ingredient_id,
            "quantity": quantity, "unit": unit}


def test_single_ingredient(tables):
    d = ingredient_details(item("paneer", 200, "g"), tables)
    assert d["grams"] == 200
    assert d["kcal"] == 600 and d["protein_g"] == 44
    assert d["cost_inr"] == pytest.approx(80)


def test_recipe_totals_and_per_serving(tables):
    ingredients = [item("paneer", 200, "g"), item("egg", 2, "piece"), item("oil", 10, "g"),
                   {"name": "salt to taste", "ingredient_id": "salt", "quantity": None,
                    "unit": None}]
    r = calculate_recipe(ingredients, tables, servings=2)
    # paneer 600 + eggs 143 + oil 88.4 = 831.4 kcal
    assert r["total"]["kcal"] == 831
    assert r["per_serving"]["kcal"] == 416
    assert r["per_serving"]["protein_g"] == pytest.approx((44 + 12.6) / 2, abs=0.1)
    assert r["servings_estimated"] is False
    assert r["coverage"] == 1.0  # salt "to taste" is not counted against us
    assert r["confidence"] == "high"
    assert r["cost_inr_total"] == pytest.approx(80 + 14 + 1.63, abs=0.01)


def test_unknown_items_lower_confidence(tables):
    ingredients = [item("paneer", 200, "g"), item(None, 1, "cup", name="dragonfruit"),
                   item("egg", 1, "package")]
    r = calculate_recipe(ingredients, tables, servings=1)
    assert r["coverage"] == pytest.approx(0.33, abs=0.01)
    assert r["confidence"] == "low"
    assert "dragonfruit (unknown_ingredient)" in r["problems"]
    assert "egg (unknown_amount)" in r["problems"]


def test_negligible_items_cost_nothing(tables):
    d = ingredient_details(item("water", 1, "cup"), tables)
    assert d["kcal"] == 0 and d["cost_inr"] == 0


def test_servings_are_estimated_when_missing(tables):
    r = calculate_recipe([item("paneer", 500, "g")], tables, course="main")  # 1500 kcal
    assert r["servings"] == 3 and r["servings_estimated"] is True


@pytest.mark.parametrize(
    ("kcal", "course", "expected"),
    [(1500, "main", 3), (100, "main", 1), (99999, "main", 12), (600, "dessert", 2)],
)
def test_estimate_servings(kcal, course, expected):
    assert estimate_servings(kcal, course) == expected
    