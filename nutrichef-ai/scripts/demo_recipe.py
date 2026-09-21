"""Scenario 1 end to end: one request -> a checked recipe.

Run from the project root (uses your Gemini key):
    python -m scripts.demo_recipe
    python -m scripts.demo_recipe --request "quick vegan breakfast under 400 calories"
"""

import argparse

from app.core.logging import configure_logging
from app.services.recipe_service import generate_recipe

DEFAULT_REQUEST = ("I am vegetarian, allergic to soy, don't want whey, have paneer, eggs and "
                   "vegetables at home, and want a high-protein dinner under 600 calories.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", default=DEFAULT_REQUEST)
    parser.add_argument("--no-search", action="store_true", help="skip the RAG search")
    args = parser.parse_args()
    configure_logging()

    from app.services.recipe_service import load_dependencies

    deps = load_dependencies(use_search=not args.no_search)
    result = generate_recipe(args.request, deps=deps)

    print(f"\nREQUEST: {args.request}\n")
    print("STEPS TAKEN")
    for step in result["trace"]:
        print(f"  {step['seconds']:6.1f}s  {step['step']:12} {step['detail'][:80]}")

    recipe = result["recipe"]
    print(f"\nSTATUS: {result['status']}  (revisions: {result['revisions']})")
    print(f"\n{recipe['title']} - serves {recipe['servings']}")
    for line in recipe["ingredients"]:
        print(f"  - {line}")
    for i, step in enumerate(recipe["steps"], 1):
        print(f"  {i}. {step}")

    print(f"\nPER SERVING: {result['nutrition_per_serving']}")
    print(f"COST: about Rs {result['cost_per_serving_inr']} per serving "
          f"(confidence: {result['nutrition_confidence']})")
    print(f"ALLERGENS: {recipe['allergens'] or 'none found'}")
    print(f"SUITABLE DIETS: {recipe['suitable_diets']}")
    print(f"CHECKS: {result['checks']}")
    if result["sources"]:
        print(f"INSPIRED BY: {result['sources']}")
    print(f"\n{result['disclaimer']}")


if __name__ == "__main__":
    main()
