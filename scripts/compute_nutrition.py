"""Add nutrition and cost to every processed recipe.

Run from the project root (after scripts.build_ingredient_foods and scripts.process_recipes):
    python -m scripts.compute_nutrition

Output: data/processed/recipes_nutrition.jsonl
"""

import pandas as pd

from app.core.config import PROJECT_ROOT
from app.nutrition.calculator import INGREDIENT_FOODS_PATH, calculate_recipe, load_tables
from app.processing.recipes import RECIPES_PATH

OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "recipes_nutrition.jsonl"
MAX_KCAL_PER_SERVING = 2000  # anything above this is probably a parsing mistake


def add_nutrition(recipe, tables):
    servings = recipe["servings"] if pd.notna(recipe["servings"]) else None
    result = calculate_recipe(recipe["ingredients"], tables, servings, recipe["course"])

    recipe["servings"] = result["servings"]
    recipe["servings_estimated"] = result["servings_estimated"]
    recipe["total_grams"] = result["total_grams"]
    for name, value in result["per_serving"].items():
        recipe[name] = value  # per-serving kcal, protein_g, carbs_g, fat_g, fiber_g
    recipe["cost_per_serving_inr"] = result["cost_inr_per_serving"]
    recipe["cost_coverage"] = result["cost_coverage"]
    recipe["nutrition_coverage"] = result["coverage"]
    recipe["nutrition_confidence"] = result["confidence"]

    looks_wrong = result["per_serving"]["kcal"] > MAX_KCAL_PER_SERVING
    recipe["library_ready"] = bool(
        recipe["library_ready"] and result["confidence"] == "high" and not looks_wrong
    )
    return recipe


def main():
    if not INGREDIENT_FOODS_PATH.exists() or not RECIPES_PATH.exists():
        print("Run scripts.build_ingredient_foods and scripts.process_recipes first.")
        return

    tables = load_tables()
    recipes = pd.read_json(RECIPES_PATH, lines=True)
    rows = [add_nutrition(row.to_dict(), tables) for _, row in recipes.iterrows()]
    df = pd.DataFrame(rows)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_json(OUTPUT_PATH, orient="records", lines=True, force_ascii=False)
    print(f"Saved {len(df):,} recipes -> {OUTPUT_PATH}\n")

    print("Nutrition confidence:")
    print(df["nutrition_confidence"].value_counts().to_string())
    print(f"\nLibrary-ready recipes: {df['library_ready'].sum():,}")

    ready = df[df["library_ready"]]
    print("\nPer-serving values of library-ready recipes:")
    print(ready[["kcal", "protein_g", "carbs_g", "fat_g", "cost_per_serving_inr"]]
          .describe().round(1).to_string())

    print("\nCurated Indian recipes (check these look sensible):")
    curated = df[df["origin"] == "curated"]
    columns = ["title", "servings", "kcal", "protein_g", "carbs_g", "fat_g", "fiber_g",
               "cost_per_serving_inr", "nutrition_confidence"]
    print(curated[columns].to_string(index=False))


if __name__ == "__main__":
    main()
