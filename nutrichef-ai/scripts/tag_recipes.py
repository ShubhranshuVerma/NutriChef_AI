"""Add allergen, food-group and diet tags to every recipe.

Run from the project root (after scripts.compute_nutrition):
    python -m scripts.tag_recipes

Output: data/processed/recipes_tagged.jsonl
"""

from collections import Counter

import pandas as pd

from app.core.config import PROJECT_ROOT
from app.validation.checks import load_rules, nutrition_looks_wrong, tag_recipe
from scripts.compute_nutrition import OUTPUT_PATH as NUTRITION_PATH

OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "recipes_tagged.jsonl"


def main():
    if not NUTRITION_PATH.exists():
        print("Run scripts.compute_nutrition first.")
        return

    rules = load_rules()
    recipes = pd.read_json(NUTRITION_PATH, lines=True)
    rows = []
    for _, row in recipes.iterrows():
        recipe = tag_recipe(row.to_dict(), rules)
        if nutrition_looks_wrong(recipe):
            recipe["library_ready"] = False
            recipe["nutrition_confidence"] = "low"
        rows.append(recipe)

    df = pd.DataFrame(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_json(OUTPUT_PATH, orient="records", lines=True, force_ascii=False)
    print(f"Saved {len(df):,} tagged recipes -> {OUTPUT_PATH}\n")

    allergens = Counter(a for tags in df["allergens"] for a in tags)
    print("Recipes containing each allergen:")
    for code, count in allergens.most_common():
        print(f"  {code:14} {count:6,}")

    diets = Counter(d for tags in df["suitable_diets"] for d in tags)
    print("\nRecipes suitable for each diet:")
    for diet, count in diets.most_common():
        print(f"  {diet:16} {count:6,}")

    print(f"\nLibrary-ready recipes: {df['library_ready'].sum():,}")
    print(f"Dropped for impossible nutrition: "
          f"{sum(nutrition_looks_wrong(r) for r in rows):,}")

    print("\nCurated Indian recipes:")
    curated = df[df["origin"] == "curated"].head(10)
    for row in curated.itertuples():
        print(f"  {row.title:22} allergens={row.allergens} diets={row.suitable_diets}")


if __name__ == "__main__":
    main()
