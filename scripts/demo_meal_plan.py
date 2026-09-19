"""Scenario 2 end to end: a 7-day meal plan inside a budget, using what you have.

Run from the project root (after scripts.tag_recipes):
    python -m scripts.demo_meal_plan
    python -m scripts.demo_meal_plan --days 3 --budget 800
    python -m scripts.demo_meal_plan --no-llm          # skip the LLM, use fixed constraints
"""

import argparse

from app.agents.agents import extract_requirements
from app.core.llm import get_llm
from app.core.logging import configure_logging
from app.services import planner

DEFAULT_REQUEST = ("Create a 7-day vegetarian high-protein meal plan under Rs 1500 "
                   "using ingredients I already have.")

# Fixed constraints for --no-llm, so the demo also runs offline.
FALLBACK_REQUEST = {"diet": "vegetarian", "allergies": [], "exclude": [], "min_protein_g": 25}

DAILY_KCAL = 2000  # a normal day, used only to aim for sensibly sized meals

# What is in the fridge today. In the app this comes from the user's inventory.
PANTRY = [
    {"ingredient_id": "paneer", "grams": 400, "expires_in_days": 2},
    {"ingredient_id": "spinach", "grams": 250, "expires_in_days": 2},
    {"ingredient_id": "curd", "grams": 400, "expires_in_days": 5},
    {"ingredient_id": "onion", "grams": 500},
    {"ingredient_id": "tomato", "grams": 400},
    {"ingredient_id": "rice", "grams": 1000},
    {"ingredient_id": "oats", "grams": 500},
    {"ingredient_id": "besan", "grams": 500},
]


def understand(text, use_llm):
    """Free text -> the request dict the checks use, and a profile for the ranker."""
    if not use_llm:
        return dict(FALLBACK_REQUEST)
    constraints = extract_requirements(text, get_llm())
    return {"diet": constraints.diet, "allergies": constraints.allergies,
            "exclude": constraints.exclude, "min_protein_g": constraints.min_protein_g,
            "max_kcal": constraints.max_kcal, "max_cook_minutes": constraints.max_cook_minutes}


def user_profile(request, budget_inr, meals, days):
    """What the ranker uses. Without a calorie limit we aim for a normal-sized day."""
    per_meal_kcal = DAILY_KCAL / (meals / days) if meals else None
    return {
        "diet": request.get("diet"),
        "protein_target_g": request.get("min_protein_g"),
        "kcal_target": request.get("max_kcal") or round(per_meal_kcal),
        "budget_per_meal_inr": round(budget_inr / meals, 2) if budget_inr and meals else None,
        "max_cook_minutes": request.get("max_cook_minutes"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", default=DEFAULT_REQUEST)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--budget", type=float, default=1500)
    parser.add_argument("--slots", default=",".join(planner.DEFAULT_SLOTS),
                        help="meals per day, e.g. breakfast,lunch,dinner,snack")
    parser.add_argument("--no-llm", action="store_true", help="skip the LLM step")
    args = parser.parse_args()
    configure_logging()

    deps = planner.load_dependencies()
    request = understand(args.request, use_llm=not args.no_llm)
    slots = [s.strip() for s in args.slots.split(",") if s.strip()]
    profile = user_profile(request, args.budget, args.days * len(slots), args.days)

    plan = planner.make_plan(deps["recipes"], profile, request, deps["rules"], deps["tables"],
                             days=args.days, slots=slots, budget_inr=args.budget,
                             inventory=PANTRY)

    print(f"\nREQUEST: {args.request}")
    print(f"UNDERSTOOD AS: {request}")
    print(f"\nRecipes in the library: {plan['recipes_considered']:,}  |  "
          f"safe for you: {plan['recipes_safe']:,}  |  "
          f"safe and priced: {plan['recipes_allowed']:,}")

    print("\nPLAN")
    for day in range(1, args.days + 1):
        print(f"\n  Day {day}")
        for meal in [m for m in plan["meals"] if m["day"] == day]:
            print(f"    {meal['slot']:10} {meal['title'][:38]:40} "
                  f"{meal['kcal'] or 0:5.0f} kcal  {meal['protein_g'] or 0:5.1f} g protein  "
                  f"Rs {meal['cost_inr'] or 0:6.2f}")

    totals = plan["totals"]
    print(f"\nTOTALS: {totals['meals']} meals, Rs {totals['total_cost_inr']} "
          f"(budget Rs {args.budget:.0f}, within budget: {plan['within_budget']})")
    print(f"PER DAY: about {totals['avg_kcal_per_day']} kcal and "
          f"{totals['avg_protein_per_day']} g protein")
    if request.get("min_protein_g"):
        target = request["min_protein_g"] * len(slots)
        met = "met" if totals["avg_protein_per_day"] >= target else "NOT met"
        print(f"PROTEIN TARGET: {target} g per day ({request['min_protein_g']} g x "
              f"{len(slots)} meals) - {met}")
    if plan["skipped"]:
        print(f"NOT FILLED: {len(plan['skipped'])} slots "
              f"(e.g. {plan['skipped'][0]['slot']} on day {plan['skipped'][0]['day']})")

    print("\nSHOPPING LIST (top 15 by cost)")
    rows = sorted(plan["shopping_list"], key=lambda r: r["cost_inr"] or 0, reverse=True)
    for row in rows[:15]:
        if row["to_buy_g"] <= 0:
            continue
        cost = f"Rs {row['cost_inr']:.2f}" if row["cost_inr"] is not None else "price unknown"
        print(f"  {row['ingredient_id']:18} buy {row['to_buy_g']:6} g   "
              f"(need {row['needed_g']}, at home {row['at_home_g']})   {cost}")

    summary = plan["shopping_summary"]
    print(f"\nTO BUY: {summary['items_to_buy']} items, about Rs {summary['cost_inr']}")
    print(f"SAVED BY USING WHAT YOU HAVE: about Rs "
          f"{summary['saved_by_using_what_you_have_inr']}")
    print("\nNutrition and costs are estimates. NutriChef is a general wellness tool, "
          "not medical advice, and cannot guarantee allergy safety.")


if __name__ == "__main__":
    main()
