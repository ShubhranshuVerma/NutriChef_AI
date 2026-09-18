"""Show the status of every NutriChef data source.

Run from the project root:
    python -m scripts.check_data
"""

import sys

from app.core.config import get_settings
from app.datasets import recipenlg, reference, usda
from app.nutrition.food_matcher import load_catalog

OK, MISSING = "[ OK ]", "[MISS]"


def main() -> int:
    ready = True

    print("Reference tables (committed):")
    checks = {
        "allergens": reference.load_allergens,
        "allergen keywords": reference.load_allergen_keywords,
        "food group keywords": reference.load_food_group_keywords,
        "keyword exceptions": reference.load_keyword_exceptions,
        "diets": reference.load_diets,
        "prices (INR)": reference.load_prices,
        "curated Indian recipes": reference.load_curated_recipes,
        "ingredient catalog": load_catalog,
    }
    for name, loader in checks.items():
        print(f"  {OK} {name:<24} {len(loader()):>5} rows")
    kb = reference.knowledge_base_files()
    print(f"  {OK} {'knowledge base docs':<24} {len(kb):>5} files")

    print("\nDownloaded / generated data (git-ignored):")
    if usda.OUTPUT_PATH.exists():
        rows = sum(1 for _ in open(usda.OUTPUT_PATH, encoding="utf-8")) - 1
        print(f"  {OK} USDA foods               {rows:>5} rows  ({usda.OUTPUT_PATH.name})")
    else:
        ready = False
        print(f"  {MISSING} USDA foods - run: python -m scripts.download_usda")

    csv = get_settings().recipenlg_csv_path
    if csv.exists():
        print(f"  {OK} RecipeNLG CSV            {csv.stat().st_size / 1e9:.2f} GB ({csv.name})")
    else:
        ready = False
        print(f"  {MISSING} RecipeNLG CSV - download it and set RECIPENLG_CSV_PATH")

    if recipenlg.SAMPLE_PATH.exists():
        print(f"  {OK} RecipeNLG sample         ({recipenlg.SAMPLE_PATH.name})")
    else:
        ready = False
        print(f"  {MISSING} RecipeNLG sample - run: python -m scripts.sample_recipenlg")

    from app.processing.recipes import RECIPES_PATH
    from scripts.build_ingredient_foods import OUTPUT_PATH as FOODS_MAP
    from scripts.compute_nutrition import OUTPUT_PATH as NUTRITION_PATH
    from app.ml.ranker import MODEL_PATH
    from scripts.simulate_users import INTERACTIONS_PATH
    from scripts.tag_recipes import OUTPUT_PATH as TAGGED_PATH

    for label, path, command in [
        ("ingredient -> USDA map", FOODS_MAP, "scripts.build_ingredient_foods"),
        ("processed recipes", RECIPES_PATH, "scripts.process_recipes"),
        ("recipes with nutrition", NUTRITION_PATH, "scripts.compute_nutrition"),
        ("tagged recipes", TAGGED_PATH, "scripts.tag_recipes"),
        ("simulated interactions", INTERACTIONS_PATH, "scripts.simulate_users"),
        ("ranking model", MODEL_PATH, "scripts.train_ranker"),
        ("search index (Chroma)", get_settings().chroma_dir, "scripts.build_index"),
    ]:
        if path.exists():
            print(f"  {OK} {label:<24} ({path.name})")
        else:
            ready = False
            print(f"  {MISSING} {label} - run: python -m {command}")

    print("\nAll data ready." if ready else "\nSome data is missing - see [MISS] lines.")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
