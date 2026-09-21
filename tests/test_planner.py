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


def test_a_slot_nothing_can_fill_is_left_empty_and_says_why(library):
    mains_only = [r for r in library if r["course"] == "main"]
    plan = planner.plan_meals(mains_only, {}, days=1, slots=["snack"])
    assert plan["meals"] == []
    assert plan["skipped"] == [{"day": 1, "slot": "snack", "reason": "no_recipe"}]


def test_no_breakfast_left_means_a_light_stand_in_not_an_empty_slot(library):
    """A soy allergy and a dislike or two can remove every breakfast in the library."""
    library.append(make_recipe("s1", "Sprouts Chaat", course="snack", cost=20))
    no_breakfasts = [r for r in library if r["course"] != "breakfast"]
    plan = planner.plan_meals(no_breakfasts, {}, days=3, slots=["breakfast", "lunch"])
    breakfasts = [m for m in plan["meals"] if m["slot"] == "breakfast"]
    assert plan["skipped"] == []
    assert [m["title"] for m in breakfasts] == ["Sprouts Chaat"] * 3
    assert all(m["stand_in"] for m in breakfasts)


def test_the_budget_is_paced_so_the_last_days_are_not_empty():
    """Spending on a pricey favourite on day 1 must not leave day 3 with nothing."""
    pricey = make_recipe("p", "Paneer Tikka", cost=100, protein_g=40)
    cheap = make_recipe("c", "Dal Rice", cost=10, protein_g=12)
    plan = planner.plan_meals([pricey, cheap], {"protein_target_g": 30}, days=3,
                              slots=["lunch"], budget_inr=115)
    assert plan["skipped"] == []
    assert plan["totals"]["total_cost_inr"] <= 115


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


# ---------- personal: what they liked and disliked ----------

def test_a_disliked_recipe_never_comes_back(library):
    plan = planner.make_plan({}, days=7, slots=["lunch", "dinner"], deps=deps(library),
                             feedback={"disliked": ["r1"]})
    assert "r1" not in [m["recipe_id"] for m in plan["meals"]]


def test_a_liked_recipe_and_similar_ones_rank_higher(library):
    library[2]["cuisine_group"] = "italian"          # Chana Masala: nothing like Paneer Bhurji
    user = planner.personalize({}, library, {"liked": ["r1"]})
    assert user["liked_ingredients"] == ["onion", "paneer"]
    scores = {r["recipe_id"]: r["score"] for r in planner.score_recipes(library, user, [])}
    assert scores["r1"] > scores["r2"] > scores["r3"]  # liked > shares onion > shares nothing


def test_ratings_turn_the_ranking_model_on(library):
    """With no ratings the model is ignored; after five it has full weight."""
    class LovesEverything:
        def predict_proba(self, rows):
            return [[0.0, 1.0] for _ in range(len(rows))]

    five = {"liked": ["r1", "r2"], "disliked": ["r3", "r4", "r5"]}
    new = planner.score_recipes(library, planner.personalize({}, library, None), [],
                                model=LovesEverything())
    rated = planner.score_recipes(library, planner.personalize({}, library, five), [],
                                  model=LovesEverything())
    score = lambda plan, rid: next(r["score"] for r in plan if r["recipe_id"] == rid)
    assert score(rated, "r6") > score(new, "r6")      # the model's "yes" now counts
