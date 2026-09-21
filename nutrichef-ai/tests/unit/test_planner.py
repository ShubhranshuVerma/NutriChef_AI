"""Tests for the meal planner. No LLM, no data files - small recipes made by hand."""

import pytest

from app.services import planner
from app.validation.checks import load_rules


def recipe(recipe_id, title, course="main", kcal=500, protein_g=30, cost=40,
           ingredient_ids=None, allergens=None, diets=None, cost_coverage=1.0):
    """A tagged recipe with just the fields the planner uses."""
    ingredient_ids = ingredient_ids or ["paneer", "onion"]
    return {
        "recipe_id": recipe_id, "title": title, "course": course, "origin": "curated",
        "kcal": kcal, "protein_g": protein_g, "carbs_g": 20, "fat_g": 15,
        "cost_per_serving_inr": cost, "cook_minutes": 30, "servings": 2,
        "cuisine_group": "indian", "n_ingredients": len(ingredient_ids),
        "ingredient_ids": ingredient_ids,
        "ingredients": [{"name": i, "ingredient_id": i, "quantity": 100, "unit": "g"}
                        for i in ingredient_ids],
        "allergens": allergens if allergens is not None else [],
        "food_groups": ["dairy"] if not diets else [],
        "suitable_diets": diets if diets is not None else ["vegetarian", "eggetarian"],
        "nutrition_confidence": "high", "library_ready": True,
        "cost_coverage": cost_coverage,
    }


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture
def recipes():
    return [
        recipe("r1", "Paneer Bhurji", ingredient_ids=["paneer", "onion"]),
        recipe("r2", "Rajma Masala", ingredient_ids=["kidney_bean", "onion"]),
        recipe("r3", "Chana Masala", ingredient_ids=["chickpea", "tomato"]),
        recipe("r4", "Besan Chilla", course="breakfast", kcal=350,
               ingredient_ids=["gram_flour", "onion"]),
        recipe("r5", "Poha", course="breakfast", kcal=320, ingredient_ids=["rice", "peanut"]),
        recipe("r6", "Oats Upma", course="breakfast", kcal=300, ingredient_ids=["oats", "carrot"]),
    ]


FAKE_TABLES = {
    "catalog": {name: {"density_g_ml": None, "grams_per_piece": None, "category": "vegetable",
                       "nutrition_source": "usda"}
                for name in ["paneer", "onion", "kidney_bean", "chickpea", "tomato",
                             "gram_flour", "rice", "peanut", "oats", "carrot"]},
    "price_per_gram": {"paneer": 0.4, "onion": 0.05},
}


# ---------- safety filter ----------

def test_unsafe_recipes_are_dropped(recipes, rules):
    recipes[0]["allergens"] = ["milk"]
    kept = planner.safe_recipes(recipes, {"allergies": ["milk"]}, rules)
    assert [r["recipe_id"] for r in kept] == ["r2", "r3", "r4", "r5", "r6"]


def test_diet_is_a_hard_rule(recipes, rules):
    recipes[0]["food_groups"] = ["meat"]
    kept = planner.safe_recipes(recipes, {"diet": "vegetarian"}, rules)
    assert "r1" not in [r["recipe_id"] for r in kept]


def test_falsely_cheap_recipes_are_left_out_when_there_is_a_budget(rules):
    """A recipe with almost no prices looks free, so it must not win on cost."""
    honest = [recipe(f"h{i}", f"Honest {i}", cost=40) for i in range(6)]
    fake_cheap = recipe("x1", "Mystery Casserole", cost=2, cost_coverage=0.3)
    plan = planner.make_plan(honest + [fake_cheap], {}, {}, rules, FAKE_TABLES,
                             days=2, slots=["lunch"], budget_inr=500, use_model=False)
    assert plan["recipes_safe"] == 7
    assert plan["recipes_allowed"] == 6
    assert "x1" not in [m["recipe_id"] for m in plan["meals"]]


def test_pricing_filter_is_skipped_if_it_would_empty_the_library(rules):
    """Better an uncertain price than no plan at all."""
    poorly_priced = [recipe(f"p{i}", f"Poor {i}", cost_coverage=0.2) for i in range(3)]
    plan = planner.make_plan(poorly_priced, {}, {}, rules, FAKE_TABLES,
                             days=3, slots=["lunch"], budget_inr=500, use_model=False)
    assert plan["recipes_allowed"] == 3
    assert len(plan["meals"]) == 3


# ---------- scoring ----------

def test_inventory_raises_the_score(recipes):
    user = {"diet": "vegetarian"}
    without = planner.score_recipes(recipes, user, inventory=None)
    with_paneer = planner.score_recipes(recipes, user, inventory=["paneer"])
    before = {r["recipe_id"]: r["score"] for r in without}
    after = {r["recipe_id"]: r["score"] for r in with_paneer}
    assert after["r1"] > before["r1"]
    assert after["r3"] == before["r3"]  # uses nothing we have


def test_protein_target_only_helps_recipes_that_reach_it():
    rich = recipe("r1", "Paneer Bhurji", protein_g=30)
    poor = recipe("r2", "Aloo Sabzi", protein_g=8)
    user = {"diet": "vegetarian", "protein_target_g": 25}
    before = {r["recipe_id"]: r["score"]
              for r in planner.score_recipes([rich, poor], {"diet": "vegetarian"}, None)}
    after = {r["recipe_id"]: r["score"] for r in planner.score_recipes([rich, poor], user, None)}
    assert after["r1"] - before["r1"] >= planner.PROTEIN_BONUS   # bonus + a better protein fit
    assert after["r2"] <= before["r2"]                           # no bonus, worse protein fit


def test_expiring_food_is_preferred(recipes):
    user = {"diet": "vegetarian"}
    normal = planner.score_recipes(recipes, user, inventory=[{"ingredient_id": "paneer"}])
    urgent = planner.score_recipes(
        recipes, user, inventory=[{"ingredient_id": "paneer", "expires_in_days": 1}])
    assert urgent[0]["recipe_id"] == "r1"
    assert dict((r["recipe_id"], r["score"]) for r in urgent)["r1"] > \
        dict((r["recipe_id"], r["score"]) for r in normal)["r1"]


# ---------- the plan ----------

def test_plan_fills_every_slot(recipes):
    plan = planner.plan_meals(recipes, {"diet": "vegetarian"}, days=3)
    assert len(plan["meals"]) == 9
    assert plan["skipped"] == []


def test_no_repeat_within_the_window():
    mains = [recipe(f"m{i}", f"Main {i}", cost=30 + i) for i in range(6)]
    plan = planner.plan_meals(mains, {"diet": "vegetarian"}, days=7, slots=["lunch", "dinner"])
    last_seen = {}
    for meal in plan["meals"]:
        previous = last_seen.get(meal["recipe_id"])
        if previous is not None:
            assert meal["day"] - previous >= planner.NO_REPEAT_DAYS
        last_seen[meal["recipe_id"]] = meal["day"]


def test_new_recipes_come_before_repeats():
    """With enough recipes, a 7-day plan should not repeat anything at all."""
    mains = [recipe(f"m{i}", f"Main {i}", cost=30 + i) for i in range(20)]
    plan = planner.plan_meals(mains, {"diet": "vegetarian"}, days=7, slots=["lunch", "dinner"])
    used = [m["recipe_id"] for m in plan["meals"]]
    assert len(set(used)) == len(used) == 14


def test_never_the_same_recipe_twice_in_one_day(recipes):
    """With a small library repeats are allowed across days, but never within a day."""
    plan = planner.plan_meals(recipes, {"diet": "vegetarian"}, days=7)
    seen = set()
    for meal in plan["meals"]:
        key = (meal["day"], meal["recipe_id"])
        assert key not in seen
        seen.add(key)


def test_budget_is_respected(recipes):
    plan = planner.plan_meals(recipes, {"diet": "vegetarian"}, days=7, budget_inr=300)
    assert plan["totals"]["total_cost_inr"] <= 300
    assert plan["skipped"]  # not every slot can be filled on a small budget


def test_missing_course_is_skipped_not_faked(recipes):
    plan = planner.plan_meals(recipes, {}, days=1, slots=["snack"])
    assert plan["meals"] == []
    assert plan["skipped"][0]["slot"] == "snack"


def test_totals():
    meals = [{"cost_inr": 40, "kcal": 500, "protein_g": 30},
             {"cost_inr": 20, "kcal": 300, "protein_g": 10}]
    totals = planner.plan_totals(meals, days=2)
    assert totals == {"meals": 2, "total_cost_inr": 60.0,
                      "avg_kcal_per_day": 400.0, "avg_protein_per_day": 20.0}


# ---------- shopping list ----------

def test_shopping_list_subtracts_what_is_at_home():
    meals = [{"servings": 2, "ingredients": [
        {"ingredient_id": "paneer", "quantity": 200, "unit": "g"},
        {"ingredient_id": "onion", "quantity": 100, "unit": "g"},
    ]}]
    rows = planner.shopping_list(meals, [{"ingredient_id": "paneer", "grams": 60}], FAKE_TABLES)
    paneer = next(r for r in rows if r["ingredient_id"] == "paneer")
    assert paneer["needed_g"] == 100      # 200 g for 2 servings -> 100 g for one
    assert paneer["at_home_g"] == 60
    assert paneer["to_buy_g"] == 40
    assert paneer["cost_inr"] == 16.0     # 40 g * 0.4
    assert paneer["saved_inr"] == 24.0    # 60 g * 0.4


def test_shopping_summary():
    rows = [{"to_buy_g": 40, "cost_inr": 16.0, "saved_inr": 24.0},
            {"to_buy_g": 0, "cost_inr": 0.0, "saved_inr": 5.0}]
    assert planner.shopping_summary(rows) == {
        "items_to_buy": 1, "cost_inr": 16.0, "saved_by_using_what_you_have_inr": 29.0}


# ---------- everything together ----------

def test_make_plan(recipes, rules):
    request = {"diet": "vegetarian", "allergies": ["peanut"], "min_protein_g": 25}
    recipes[4]["allergens"] = ["peanut"]  # Poha
    plan = planner.make_plan(recipes, {"diet": "vegetarian"}, request, rules, FAKE_TABLES,
                             days=7, budget_inr=1500,
                             inventory=[{"ingredient_id": "paneer", "grams": 400}],
                             use_model=False)
    assert plan["recipes_considered"] == 6
    assert plan["recipes_allowed"] == 5
    assert "r5" not in [m["recipe_id"] for m in plan["meals"]]
    assert plan["within_budget"]
    assert plan["shopping_summary"]["saved_by_using_what_you_have_inr"] > 0
