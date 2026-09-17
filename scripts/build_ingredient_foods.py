"""Link every catalog ingredient to a USDA food and save its nutrients per 100 g.

Run from the project root (after scripts.download_usda):
    python -m scripts.build_ingredient_foods

Output: data/processed/ingredient_foods.csv
Review the report: 'fuzzy' rows used the closest USDA description and 'missing'
rows need a fix. To fix one, either correct `usda_description` or put the exact
FoodData Central id in the `usda_fdc_id` column of data/reference/ingredient_catalog.csv
(search the id in data/processed/usda_foods.csv).
"""

import sys

import pandas as pd

from app.core.config import PROJECT_ROOT
from app.datasets import usda
from app.nutrition.food_matcher import load_catalog, resolve_usda

OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "ingredient_foods.csv"


def main() -> int:
    if not usda.OUTPUT_PATH.exists():
        print("USDA foods not found - run: python -m scripts.download_usda")
        return 1
    foods = pd.read_csv(usda.OUTPUT_PATH)
    table = resolve_usda(load_catalog(), foods)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT_PATH, index=False)

    print(f"Saved {len(table)} ingredients -> {OUTPUT_PATH}\n")
    print(table["match_type"].value_counts().to_string(), "\n")
    review = table[table["match_type"].isin(["fuzzy", "missing"])]
    if not review.empty:
        print("Please review (requested -> used):")
        for row in review.itertuples():
            print(f"  [{row.match_type:7}] {row.ingredient_id:18} "
                  f"{row.requested_description!r} -> {row.usda_description!r}")
    prefix = table[table["match_type"] == "prefix"]
    if not prefix.empty:
        print("\nMore specific USDA foods used (usually fine):")
        for row in prefix.itertuples():
            print(f"  [prefix ] {row.ingredient_id:18} -> {row.usda_description!r}")
    proxies = table[table["nutrition_source"] == "usda_proxy"]
    print(f"\n{len(proxies)} ingredients use a proxy food (see notes in the catalog).")
    return 0 if (table["match_type"] != "missing").all() else 2


if __name__ == "__main__":
    sys.exit(main())
