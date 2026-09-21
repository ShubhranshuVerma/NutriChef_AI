"""The meal planner (Scenario 2). Hand-made recipes, no data files, no LLM."""

import pytest

from app.nutrition.checks import load_rules
from app.services import planner
from tests.helpers import PLAN_TABLES, make_recipe, small_library


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture
def library():
    return small_library()


def deps(recipes):
    return {"recipes": recipes, "rules": load_rules(), "tables": PLAN_TABLES}


# ---------- only safe recipes ----------

def test_an_allergen_keeps_a_recipe_out_of_the_plan(library, rules):
    library[4]["allergens"] = ["peanut"]                        # Poha
    safe = planner.safe_recipes(library, {"allergies": ["peanut"]}, rules)
    assert "r5" not in [r["recipe_id"] for r in safe]


def test_the_diet_is_a_hard_rule(library, rules):
    library[0]["food_groups"] = ["meat"]           # judged from the ingredients, not a label
    safe = planner.safe_recipes(library, {"diet": "vegetarian"}, rules)
    assert "r1" not in [r["recipe_id"] for r in safe]


def test_recipes_we_cannot_price_do_not_look_free():
    """Unpriced ingredients count as Rs 0, so a badly priced recipe looks cheapest."""
    honest = make_recipe("r1", "Honest", cost=40)
    looks_free = make_recipe("r2", "Looks Free", cost=2, cost_coverage=0.3)
    assert planner.priced_well([honest, looks_free]) == [honest]


# ---------- filling the week ----------

def test_the_budget_is_never_exceeded(library):
    plan = planner.plan_meals(library, {"diet": "vegetarian"}, days=7, budget_inr=300)
    assert plan["totals"]["total_cost_inr"] <= 300
    assert plan["skipped"]              # a small budget cannot fill every slot


def test_a_budget_of_nothing_buys_nothing(library):
    """Zero is a real budget, not a missing one."""
    plan = planner.plan_meals(library, {}, days=1, slots=["lunch"], budget_inr=0)
    assert plan["meals"] == []
    assert plan["skipped"][0]["slot"] == "lunch"


def test_no_recipe_twice_in_one_day(library):
    plan = planner.plan_meals(library, {}, days=7, slots=["lunch", "dinner"])
    seen = set()
    for meal in plan["meals"]:
        key = (meal["day"], meal["recipe_id"])
        assert key not in seen
        seen.add(key)


def test_a_missing_course_is_skipped_not_faked(library):
    plan = planner.plan_meals(library, {}, days=1, slots=["snack"])
    assert plan["meals"] == []
    assert plan["skipped"][0]["slot"] == "snack"


# ---------- using what is at home ----------

def test_food_at_home_raises_the_score(library):
    without = {r["recipe_id"]: r["score"] for r in planner.score_recipes(library, {}, [])}
    with_paneer = {r["recipe_id"]: r["score"]
                   for r in planner.score_recipes(library, {}, ["paneer"])}
    assert with_paneer["r1"] > without["r1"]
    assert with_paneer["r2"] == without["r2"]        # no paneer in rajma


def test_the_shopping_list_subtracts_what_is_at_home():
    meals = [{"servings": 2, "ingredients": [
        {"ingredient_id": "paneer", "quantity": 200, "unit": "g"},
    ]}]
    rows = planner.shopping_list(meals, [{"ingredient_id": "paneer", "grams": 60}], PLAN_TABLES)
    paneer = rows[0]
    assert paneer["needed_g"] == 100      # 200 g for 2 servings -> 100 g for one
    assert paneer["to_buy_g"] == 40
    assert paneer["cost_inr"] == 16.0     # 40 g x Rs 0.4
    assert paneer["saved_inr"] == 24.0    # 60 g x Rs 0.4


# ---------- the whole plan ----------

def test_a_whole_plan(library):
    library[4]["allergens"] = ["peanut"]
    request = {"diet": "vegetarian", "allergies": ["peanut"], "min_protein_g": 25}
    plan = planner.make_plan(request, days=7, budget_inr=1500,
                             inventory=[{"ingredient_id": "paneer", "grams": 400}],
                             deps=deps(library))

    assert "r5" not in [m["recipe_id"] for m in plan["meals"]]
    assert plan["within_budget"]
    assert plan["protein_target_per_day_g"] == 75       # 25 g x 3 meals
    assert plan["constraints"] == request
    assert plan["shopping_summary"]["saved_by_using_what_you_have_inr"] > 0


def test_a_plan_says_whether_the_protein_goal_was_met(library):
    easy = planner.make_plan({"min_protein_g": 5}, days=2, slots=["lunch"], deps=deps(library))
    impossible = planner.make_plan({"min_protein_g": 200}, days=2, slots=["lunch"],
                                   deps=deps(library))
    assert easy["protein_target_met"] is True
    assert impossible["protein_target_met"] is False


def test_every_plan_carries_the_disclaimer(library):
    plan = planner.make_plan({}, days=1, slots=["lunch"], deps=deps(library))
    assert "not medical advice" in plan["disclaimer"]
    assert "cannot guarantee allergy safety" in plan["disclaimer"]
