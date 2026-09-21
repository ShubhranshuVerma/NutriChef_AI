"""The two demo scenarios, end to end, in the terminal.

Run from the project root:
    python -m scripts.demo recipe      # Scenario 1: one request -> a checked recipe
    python -m scripts.demo plan        # Scenario 2: a week of meals in a budget

    python -m scripts.demo recipe --request "quick vegan breakfast under 400 calories"
    python -m scripts.demo plan --days 3 --budget 800

Timing Gemini itself (each run spends 1-3 requests of your daily quota):
    python -m scripts.demo recipe --no-cache --thinking medium    # the model's default
    python -m scripts.demo recipe --no-cache --thinking low       # ours
"""

import argparse
import os

RECIPE_REQUEST = ("I am vegetarian, allergic to soy, don't want whey, have paneer, eggs and "
                  "vegetables at home, and want a high-protein dinner under 600 calories.")
PLAN_REQUEST = ("Create a 7-day vegetarian high-protein meal plan under Rs 1500 "
                "using ingredients I already have.")

# What is in the fridge today. In the app this comes from the user's saved kitchen.
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


def show_recipe(args):
    from app.services.recipe_service import generate_recipe, load_dependencies
    from app.core.config import get_settings

    request = args.request or RECIPE_REQUEST
    result = generate_recipe(request, deps=load_dependencies(use_search=not args.no_search))

    settings = get_settings()
    print(f"\nREQUEST: {request}\n")
    print(f"STEPS TAKEN  (thinking: {settings.llm_thinking or 'model default'}, "
          f"cache: {'on' if settings.llm_cache else 'off'})")
    previous = 0.0
    for step in result["trace"]:
        print(f"  {step['seconds'] - previous:6.1f}s  {step['step']:12} {step['detail'][:72]}")
        previous = step["seconds"]
    print(f"  {previous:6.1f}s  total")

    recipe = result["recipe"]
    print(f"\nSTATUS: {result['status']}  (revisions: {result['revisions']})")
    print(f"\n{recipe['title']} - serves {recipe['servings']}")
    for line in recipe["ingredients"]:
        print(f"  - {line}")
    for number, step in enumerate(recipe["steps"], 1):
        print(f"  {number}. {step}")

    print(f"\nPER SERVING: {result['nutrition_per_serving']}")
    print(f"COST: about Rs {result['cost_per_serving_inr']} per serving "
          f"(confidence: {result['nutrition_confidence']})")
    print(f"ALLERGENS: {recipe['allergens'] or 'none found'}")
    print(f"SUITABLE DIETS: {recipe['suitable_diets']}")
    print(f"CHECKS: {result['checks']}")
    if result["sources"]:
        print(f"INSPIRED BY: {result['sources']}")
    print(f"\n{result['disclaimer']}")


def show_plan(args):
    from app.services import planner

    request_text = args.request or PLAN_REQUEST
    slots = [s.strip() for s in args.slots.split(",") if s.strip()]
    request = planner.constraints_from_text(request_text)

    plan = planner.make_plan(request, days=args.days, slots=slots,
                             budget_inr=args.budget, inventory=PANTRY)

    print(f"\nREQUEST: {request_text}")
    print(f"UNDERSTOOD AS: {request}")
    print(f"\nRecipes in the library: {plan['recipes_considered']:,}  |  "
          f"safe for you: {plan['recipes_safe']:,}  |  "
          f"safe and priced: {plan['recipes_allowed']:,}")

    print("\nPLAN")
    for day in range(1, args.days + 1):
        print(f"\n  Day {day}")
        for meal in plan["meals"]:
            if meal["day"] == day:
                print(f"    {meal['slot']:10} {meal['title'][:38]:40} "
                      f"{meal['kcal'] or 0:5.0f} kcal  {meal['protein_g'] or 0:5.1f} g protein  "
                      f"Rs {meal['cost_inr'] or 0:6.2f}")

    totals = plan["totals"]
    print(f"\nTOTALS: {totals['meals']} meals, Rs {totals['total_cost_inr']} "
          f"(budget Rs {args.budget:.0f}, within budget: {plan['within_budget']})")
    print(f"PER DAY: about {totals['avg_kcal_per_day']} kcal and "
          f"{totals['avg_protein_per_day']} g protein")
    if plan["protein_target_per_day_g"]:
        met = "met" if plan["protein_target_met"] else "NOT met"
        print(f"PROTEIN TARGET: {plan['protein_target_per_day_g']} g per day "
              f"({request['min_protein_g']} g x {len(slots)} meals) - {met}")
    if plan["skipped"]:
        print(f"NOT FILLED: {len(plan['skipped'])} slots")

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
    print(f"SAVED BY USING WHAT YOU HAVE: about Rs {summary['saved_by_using_what_you_have_inr']}")
    print(f"\n{plan['disclaimer']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", choices=["recipe", "plan"])
    parser.add_argument("--request", help="your own request instead of the demo one")
    parser.add_argument("--no-search", action="store_true", help="recipe: skip the RAG search")
    parser.add_argument("--no-cache", action="store_true",
                        help="ask Gemini for real instead of replaying saved answers")
    parser.add_argument("--thinking", choices=["minimal", "low", "medium", "high"],
                        help="override LLM_THINKING for this run")
    parser.add_argument("--days", type=int, default=7, help="plan: how many days")
    parser.add_argument("--budget", type=float, default=1500, help="plan: budget in rupees")
    parser.add_argument("--slots", default="breakfast,lunch,dinner", help="plan: meals per day")
    args = parser.parse_args()

    # Settings are read once, so these have to be in place before anything else loads.
    if args.no_cache:
        os.environ["LLM_CACHE"] = "false"
    if args.thinking:
        os.environ["LLM_THINKING"] = args.thinking

    from app.core.logging import configure_logging
    from app.core.tracing import configure_tracing

    configure_logging()
    configure_tracing()
    from app.core.llm import QuotaExhausted

    try:
        if args.scenario == "recipe":
            show_recipe(args)
        else:
            show_plan(args)
    except QuotaExhausted as error:
        raise SystemExit(f"\n{error}")


if __name__ == "__main__":
    main()
