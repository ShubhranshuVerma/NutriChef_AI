"""Meal planning (Scenario 2): pick safe recipes for several days within a budget.

`make_plan` does it all, in this order:
1. keep only recipes that pass the hard checks for this person
2. score each one (ranker + what is already at home + what expires soon + protein)
3. fill the slots day by day, avoiding repeats and staying inside the budget
4. work out the shopping list: what the plan needs minus what is already at home
5. say whether the protein goal was met, and add the disclaimer

Everything here is plain Python, including step 0 (free text -> constraints),
so the same request always gives the same plan.
"""

from functools import lru_cache

import pandas as pd

from app.agents.requirements import extract_requirements
from app.core.config import PROJECT_ROOT
from app.ml.ranker import load_model, score_recipe
from app.nutrition.calculator import load_tables
from app.nutrition.checks import check_recipe, load_rules
from app.nutrition.units import to_grams

LIBRARY_PATH = PROJECT_ROOT / "data" / "processed" / "recipes_tagged.jsonl"

COURSE_FOR_SLOT = {"breakfast": "breakfast", "lunch": "main", "dinner": "main", "snack": "snack"}
# If no recipe of the right course fits someone's rules (few breakfasts survive a soy
# allergy plus a dislike or two), fill the slot from the next course instead of leaving
# it empty. The meal is marked as a stand-in so the page can say so.
COURSES_FOR_SLOT = {"breakfast": ["breakfast", "snack", "main"], "lunch": ["main"],
                    "dinner": ["main"], "snack": ["snack", "breakfast", "side"]}
DEFAULT_SLOTS = ["breakfast", "lunch", "dinner"]
DAILY_KCAL = 2000        # a normal day, used only to aim for sensibly sized meals
NO_REPEAT_DAYS = 3       # a recipe used on day 1 can come back on day 4
INVENTORY_BONUS = 0.3
EXPIRY_BONUS = 0.2
PROTEIN_BONUS = 0.4      # for recipes that actually reach the protein target
LIKED_BONUS = 0.5        # for a recipe this person has liked before
MIN_COST_COVERAGE = 0.8  # below this, most ingredients have no price and the recipe looks free
EXPIRY_SOON_DAYS = 3

DISCLAIMER = (
    "Nutrition values and prices are estimates. NutriChef is a general wellness tool, not "
    "medical advice, and cannot guarantee allergy safety - always check ingredient labels."
)


# ---------- loading ----------

@lru_cache(maxsize=1)
def load_dependencies():
    """Recipe library, rules, nutrition tables and the ranking model - read once."""
    return {"recipes": load_library(LIBRARY_PATH), "rules": load_rules(),
            "tables": load_tables(), "model": load_model()[0]}


def load_library(path=LIBRARY_PATH):
    """Read the tagged recipes and keep the ones we trust."""
    recipes = pd.read_json(path, lines=True)
    recipes = recipes[recipes["library_ready"]]
    return recipes.to_dict("records")


# ---------- the request ----------

def constraints_from_text(text):
    """Free text -> the request dict the checks use. Plain Python, no LLM."""
    constraints = extract_requirements(text)
    return {"diet": constraints.diet, "allergies": constraints.allergies,
            "exclude": constraints.exclude, "min_protein_g": constraints.min_protein_g,
            "max_kcal": constraints.max_kcal, "max_cook_minutes": constraints.max_cook_minutes}


def user_profile(request, budget_inr, days, slots):
    """What the ranker uses. Without a calorie limit we aim for a normal-sized day."""
    meals_per_day = len(slots) or 1
    budget_per_meal = None
    if budget_inr:
        budget_per_meal = round(budget_inr / (days * meals_per_day), 2)
    return {
        "diet": request.get("diet"),
        "protein_target_g": request.get("min_protein_g"),
        "kcal_target": request.get("max_kcal") or round(DAILY_KCAL / meals_per_day),
        "budget_per_meal_inr": budget_per_meal,
        "max_cook_minutes": request.get("max_cook_minutes"),
    }


def protein_target(request, slots):
    """A per-meal goal becomes a per-day goal once you know how many meals there are."""
    if not request.get("min_protein_g"):
        return None
    return request["min_protein_g"] * len(slots)


# ---------- what this person has liked ----------

def feedback_ids(feedback):
    """{"liked": [...], "disliked": [...]} -> two sets of recipe ids (empty if none)."""
    feedback = feedback or {}
    return set(feedback.get("liked", [])), set(feedback.get("disliked", []))


def personalize(user, recipes, feedback):
    """Add what their likes tell us to the ranker's profile.

    - liked_ingredients: every ingredient of every recipe they liked
    - cuisine: the cuisine they liked most (only if they did not ask for one)
    The rule score and the model both use these, so similar recipes rise too.
    """
    liked, disliked = feedback_ids(feedback)
    liked_recipes = [r for r in recipes if r["recipe_id"] in liked]
    ingredients = sorted({i for r in liked_recipes for i in (r.get("ingredient_ids") or [])})
    cuisines = [r.get("cuisine_group") for r in liked_recipes if r.get("cuisine_group")]
    favourite = max(sorted(set(cuisines)), key=cuisines.count) if cuisines else None
    return {**user, "liked_ingredients": ingredients,
            "cuisine": user.get("cuisine") or favourite,
            "liked_ids": sorted(liked), "n_interactions": len(liked) + len(disliked)}


# ---------- choosing recipes ----------

def safe_recipes(recipes, request, rules):
    """Keep only recipes that pass every hard rule for this person."""
    kept = []
    for recipe in recipes:
        if check_recipe(recipe, request, rules)["passed"]:
            kept.append(recipe)
    return kept


def priced_well(recipes, minimum=MIN_COST_COVERAGE):
    """Recipes we can actually cost.

    `cost_coverage` is the share of ingredients with a known price. A recipe at 0.3
    looks very cheap only because two thirds of it was counted as free, so it would
    always win a budget comparison against an honestly priced recipe.
    """
    return [r for r in recipes if (r.get("cost_coverage") or 0) >= minimum]


def clean_inventory(inventory):
    """Accept ["paneer", ...] or [{"ingredient_id": "paneer", "grams": 400}, ...]."""
    items = []
    for item in inventory or []:
        if isinstance(item, str):
            item = {"ingredient_id": item}
        if item.get("ingredient_id"):
            items.append(item)
    return items


def inventory_ids(inventory):
    return {item["ingredient_id"] for item in clean_inventory(inventory)}


def expiring_ids(inventory, days=EXPIRY_SOON_DAYS):
    return {item["ingredient_id"] for item in clean_inventory(inventory)
            if item.get("expires_in_days") is not None and item["expires_in_days"] <= days}


def score_recipes(recipes, user, inventory, model=None):
    """Personal score, plus bonuses for liked recipes and for using what is at home."""
    at_home = inventory_ids(inventory)
    expiring = expiring_ids(inventory)
    liked = set(user.get("liked_ids", []))
    n_interactions = user.get("n_interactions", 0)
    scored = []
    for recipe in recipes:
        ids = set(recipe.get("ingredient_ids") or [])
        score = score_recipe({**user, "inventory": list(at_home)}, recipe, model, n_interactions)
        if recipe["recipe_id"] in liked:
            score += LIKED_BONUS
        if ids & at_home:
            score += INVENTORY_BONUS * len(ids & at_home) / max(len(ids), 1)
        if ids & expiring:
            score += EXPIRY_BONUS
        target = user.get("protein_target_g")
        if target and (recipe.get("protein_g") or 0) >= target:
            score += PROTEIN_BONUS
        scored.append({**recipe, "score": round(score, 4)})
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored


def pick_recipe(scored, course, day, used_on_day, budget_left, min_gap):
    """Best-scoring recipe for this course that we can afford and have not just eaten.

    `min_gap` is how many days must pass before a recipe can come back;
    `float("inf")` means "only recipes we have not used at all".
    """
    for recipe in scored:
        if recipe.get("course") != course:
            continue
        last_used = used_on_day.get(recipe["recipe_id"])
        if last_used is not None and day - last_used < min_gap:
            continue
        cost = recipe.get("cost_per_serving_inr") or 0
        if budget_left is not None and cost > budget_left:
            continue
        return recipe
    return None


def pick_for_slot(scored, slot, day, used_on_day, budget_left):
    """The best recipe for this slot: its own course first, then the stand-in courses.

    Within a course: something new first; then a recipe we have not had for
    NO_REPEAT_DAYS; then anything we have not already eaten today.
    """
    for course in COURSES_FOR_SLOT.get(slot, ["main"]):
        for min_gap in (float("inf"), NO_REPEAT_DAYS, 1):
            choice = pick_recipe(scored, course, day, used_on_day, budget_left, min_gap)
            if choice:
                return choice
    return None


def cheapest_for(scored, slot):
    """The cheapest recipe that could fill this slot (0 if none could)."""
    costs = [r.get("cost_per_serving_inr") or 0 for r in scored
             if r.get("course") in COURSES_FOR_SLOT.get(slot, ["main"])]
    return min(costs) if costs else 0


def plan_meals(recipes, user, days=7, slots=None, budget_inr=None, inventory=None, model=None):
    """Greedy plan: for each slot pick the best recipe we can still afford.

    With a budget, each pick keeps back enough money for the cheapest possible meal in
    every slot still to fill, so the last days are not left empty because the first
    days spent it all.
    """
    slots = slots or DEFAULT_SLOTS
    scored = score_recipes(recipes, user, inventory, model)
    budget_left = budget_inr
    used_on_day = {}  # recipe_id -> last day it was used
    plan, skipped = [], []
    cheapest = {slot: cheapest_for(scored, slot) for slot in slots}
    positions = [(day, slot) for day in range(1, days + 1) for slot in slots]

    for index, (day, slot) in enumerate(positions):
        spendable = budget_left
        if budget_left is not None:
            still_to_fill = positions[index + 1:]
            spendable = budget_left - sum(cheapest[later] for _, later in still_to_fill)
        choice = pick_for_slot(scored, slot, day, used_on_day, spendable)
        if choice is None and spendable != budget_left:
            choice = pick_for_slot(scored, slot, day, used_on_day, budget_left)

        if choice is None:
            courses = COURSES_FOR_SLOT.get(slot, ["main"])
            any_fits = any(r.get("course") in courses for r in scored)
            reason = "budget" if any_fits else "no_recipe"
            skipped.append({"day": day, "slot": slot, "reason": reason})
            continue

        used_on_day[choice["recipe_id"]] = day
        if budget_left is not None:
            budget_left -= choice.get("cost_per_serving_inr") or 0
        plan.append({
            "day": day, "slot": slot, "recipe_id": choice["recipe_id"],
            "title": choice["title"], "kcal": choice.get("kcal"),
            "protein_g": choice.get("protein_g"),
            "cost_inr": choice.get("cost_per_serving_inr"),
            "score": choice["score"], "ingredient_ids": choice.get("ingredient_ids", []),
            "ingredients": choice.get("ingredients", []),
            "servings": choice.get("servings") or 1,
            "course": choice.get("course"),
            "stand_in": choice.get("course") != COURSES_FOR_SLOT.get(slot, ["main"])[0],
        })

    return {"meals": plan, "skipped": skipped, "days": days, "slots": slots,
            "budget_inr": budget_inr, "totals": plan_totals(plan, days)}


def plan_totals(meals, days):
    """Totals for the whole plan and averages per day."""
    total_cost = sum(m["cost_inr"] or 0 for m in meals)
    total_kcal = sum(m["kcal"] or 0 for m in meals)
    total_protein = sum(m["protein_g"] or 0 for m in meals)
    return {
        "meals": len(meals),
        "total_cost_inr": round(total_cost, 2),
        "avg_kcal_per_day": round(total_kcal / days, 1) if days else 0,
        "avg_protein_per_day": round(total_protein / days, 1) if days else 0,
    }


# ---------- shopping ----------

def shopping_list(meals, inventory, tables):
    """Grams needed per ingredient, minus what is at home, with a rough cost.

    Each meal in the plan is one serving, so a recipe that serves 4 only
    contributes a quarter of its ingredients.
    """
    have = {item["ingredient_id"]: item.get("grams") or 0 for item in clean_inventory(inventory)}
    needed = {}
    for meal in meals:
        servings = meal.get("servings") or 1
        for item in meal.get("ingredients", []):
            ingredient_id = item.get("ingredient_id")
            if not ingredient_id or not item.get("quantity"):
                continue
            grams = grams_of(item, tables) / servings
            if grams:
                needed[ingredient_id] = needed.get(ingredient_id, 0) + grams

    rows = []
    for ingredient_id, grams in sorted(needed.items()):
        at_home = have.get(ingredient_id, 0)
        to_buy = max(0.0, grams - at_home)
        price = tables["price_per_gram"].get(ingredient_id)
        rows.append({
            "ingredient_id": ingredient_id,
            "needed_g": round(grams),
            "at_home_g": round(at_home),
            "to_buy_g": round(to_buy),
            "cost_inr": round(to_buy * price, 2) if price else None,
            "saved_inr": round(min(grams, at_home) * price, 2) if price else None,
        })
    return rows


def grams_of(item, tables):
    """Weight of one parsed ingredient, using the catalog for densities and piece weights."""
    info = tables["catalog"].get(item.get("ingredient_id"))
    if not info:
        return 0.0
    return to_grams(item.get("quantity"), item.get("unit"), item["ingredient_id"],
                    info["density_g_ml"], info["grams_per_piece"]) or 0.0


def shopping_summary(rows):
    return {
        "items_to_buy": sum(1 for r in rows if r["to_buy_g"] > 0),
        "cost_inr": round(sum(r["cost_inr"] or 0 for r in rows), 2),
        "saved_by_using_what_you_have_inr": round(sum(r["saved_inr"] or 0 for r in rows), 2),
    }


# ---------- everything together ----------

def build_plan(recipes, user, request, rules, tables, days=7, slots=None, budget_inr=None,
               inventory=None, model=None, feedback=None):
    """Filter, score, fill the slots, and add the shopping list."""
    user = personalize(user, recipes, feedback)
    _, disliked = feedback_ids(feedback)
    # A recipe they said "not for me" to is never suggested again.
    safe = [r for r in safe_recipes(recipes, request, rules) if r["recipe_id"] not in disliked]
    allowed = safe

    # With a budget, drop recipes we cannot price properly - otherwise the ones with
    # missing prices look cheapest and win every slot.
    if budget_inr is not None:
        priced = priced_well(safe)
        if len(priced) >= days * len(slots or DEFAULT_SLOTS):
            allowed = priced

    plan = plan_meals(allowed, user, days, slots, budget_inr, inventory, model)
    rows = shopping_list(plan["meals"], inventory, tables)
    plan["shopping_list"] = rows
    plan["shopping_summary"] = shopping_summary(rows)
    plan["recipes_considered"] = len(recipes)
    plan["recipes_safe"] = len(safe)
    plan["recipes_allowed"] = len(allowed)
    plan["personalized"] = {"ratings": user["n_interactions"], "liked_cuisine": user["cuisine"]}
    plan["within_budget"] = (budget_inr is None
                             or plan["totals"]["total_cost_inr"] <= budget_inr)
    return plan


def make_plan(request, days=7, slots=None, budget_inr=None, inventory=None, deps=None,
              feedback=None):
    """The one call the API and the demo use. `request` is the constraints dict.

    `feedback` is {"liked": [recipe ids], "disliked": [recipe ids]} for a signed-in user.
    """
    deps = deps or load_dependencies()
    slots = slots or DEFAULT_SLOTS
    profile = user_profile(request, budget_inr, days, slots)

    plan = build_plan(deps["recipes"], profile, request, deps["rules"], deps["tables"],
                      days=days, slots=slots, budget_inr=budget_inr, inventory=inventory,
                      model=deps.get("model"), feedback=feedback)

    target = protein_target(request, slots)
    plan["protein_target_per_day_g"] = target
    plan["protein_target_met"] = (target is None
                                  or plan["totals"]["avg_protein_per_day"] >= target)
    plan["constraints"] = request
    plan["disclaimer"] = DISCLAIMER
    return plan
