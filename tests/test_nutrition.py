"""Reading ingredient lines, converting to grams, and adding up the nutrition.

The last three tests use your real USDA table and are skipped until it is built.
"""

import pytest

from app.nutrition.calculator import (INGREDIENT_FOODS_PATH, calculate_from_text,
                                      calculate_recipe, estimate_servings, load_tables)
from app.nutrition.parsing import parse_ingredient
from app.nutrition.units import to_grams


# ---------- reading an ingredient line ----------

@pytest.mark.parametrize(
    ("line", "quantity", "unit", "name"),
    [
        ("3 1/2 c. flour", 3.5, "cup", "flour"),
        ("200 grams paneer", 200, "g", "paneer"),
        ("10-12 almonds", 11, "piece", "almonds"),
    ],
)
def test_quantity_unit_and_name(line, quantity, unit, name):
    item = parse_ingredient(line)
    assert item.quantity == pytest.approx(quantity)
    assert item.unit == unit
    assert item.name == name


def test_one_garlic_is_one_garlic_not_one_gram_of_arlic():
    """The regex this project started from read '1 garlic' as unit 'g' + 'arlic'."""
    item = parse_ingredient("1 garlic")
    assert (item.unit, item.name) == ("piece", "garlic")


def test_a_package_size_in_brackets_is_used():
    item = parse_ingredient("1 (8 oz.) pkg. cream cheese, softened")
    assert (item.quantity, item.unit, item.name) == (8, "oz", "cream cheese")


def test_a_line_without_a_quantity():
    item = parse_ingredient("Salt to taste")
    assert item.quantity is None and item.unit is None


# ---------- grams ----------

def test_weights_volumes_and_pieces_become_grams():
    assert to_grams(1.5, "kg", "x", 1.0, 0) == 1500
    assert to_grams(1, "cup", "flour", 0.53, 0) == pytest.approx(125.4, abs=0.1)
    assert to_grams(2, "piece", "egg", 1.0, 50) == 100
    assert to_grams(1, "piece", "x", 1.0, 0) is None      # unknown piece weight


# ---------- adding it up ----------

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
    }
    nutrients = {
        "paneer": {"kcal": 300, "protein_g": 22, "carbs_g": 2, "fat_g": 22, "fiber_g": 0},
        "egg": {"kcal": 143, "protein_g": 12.6, "carbs_g": 0.7, "fat_g": 9.5, "fiber_g": 0},
        "oil": {"kcal": 884, "protein_g": 0, "carbs_g": 0, "fat_g": 100, "fiber_g": 0},
        "salt": {"kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0},
    }
    return {"catalog": catalog, "nutrients": nutrients,
            "price_per_gram": {"paneer": 0.4, "egg": 0.14, "oil": 0.163}, "matcher": None}


def item(ingredient_id, quantity, unit, name=None):
    return {"name": name or ingredient_id, "ingredient_id": ingredient_id,
            "quantity": quantity, "unit": unit}


def test_totals_and_per_serving(tables):
    ingredients = [item("paneer", 200, "g"), item("egg", 2, "piece"), item("oil", 10, "g"),
                   item("salt", None, None, name="salt to taste")]
    result = calculate_recipe(ingredients, tables, servings=2)
    # paneer 600 + eggs 143 + oil 88.4 = 831.4 kcal
    assert result["total"]["kcal"] == 831
    assert result["per_serving"]["kcal"] == 416
    assert result["confidence"] == "high"              # "salt to taste" is not held against it
    assert result["cost_inr_total"] == pytest.approx(80 + 14 + 1.63, abs=0.01)


def test_unknown_ingredients_lower_the_confidence(tables):
    ingredients = [item("paneer", 200, "g"), item(None, 1, "cup", name="dragonfruit")]
    result = calculate_recipe(ingredients, tables, servings=1)
    assert result["confidence"] == "low"
    assert "dragonfruit (unknown_ingredient)" in result["problems"]


def test_a_food_with_no_nutrition_numbers_is_not_counted_as_zero(tables):
    """A 900 kcal dish served as 600 kcal is exactly what this project must not do."""
    tables["catalog"]["jackfruit"] = {"category": "vegetable", "density_g_ml": None,
                                      "grams_per_piece": 0, "nutrition_source": "usda"}
    result = calculate_recipe([item("paneer", 200, "g"), item("jackfruit", 300, "g")],
                              tables, servings=2)
    assert result["confidence"] == "low"
    assert "jackfruit (no_nutrition_data)" in result["problems"]


def test_servings_are_estimated_when_the_recipe_does_not_say(tables):
    result = calculate_recipe([item("paneer", 500, "g")], tables, course="main")  # 1500 kcal
    assert result["servings"] == 3 and result["servings_estimated"] is True
    assert estimate_servings(600, "dessert") == 2


# ---------- against the real USDA table (skipped until it is built) ----------

needs_real_data = pytest.mark.skipif(not INGREDIENT_FOODS_PATH.exists(),
                                     reason="run: python -m scripts.build_data foods")


@needs_real_data
def test_one_egg_is_about_72_kcal():
    result = calculate_from_text(["1 egg"], load_tables(), servings=1)
    assert 60 <= result["per_serving"]["kcal"] <= 90
    assert 5 <= result["per_serving"]["protein_g"] <= 7.5


@needs_real_data
def test_paneer_bhurji_is_plausible():
    lines = ["200 g paneer", "80 g onion", "100 g tomato", "10 g oil", "2 g salt"]
    result = calculate_from_text(lines, load_tables(), servings=2)
    assert 300 <= result["per_serving"]["kcal"] <= 500
    assert result["per_serving"]["protein_g"] >= 18


@needs_real_data
def test_calories_match_the_macros():
    """Atwater: kcal is about 4 x protein + 4 x carbs + 9 x fat (within 20%)."""
    result = calculate_from_text(["1 c. flour", "1/2 c. sugar", "2 eggs", "1/2 c. butter"],
                                 load_tables(), servings=1)
    s = result["per_serving"]
    estimate = 4 * s["protein_g"] + 4 * s["carbs_g"] + 9 * s["fat_g"]
    assert abs(estimate - s["kcal"]) / s["kcal"] < 0.2
