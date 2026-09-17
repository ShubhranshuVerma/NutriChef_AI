"""Show the status of every NutriChef data source.

Run from the project root:
    python -m scripts.check_data
"""

import sys

from app.core.config import get_settings
from app.datasets import recipenlg, reference, usda

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

    print("\nAll data ready." if ready else "\nSome data is missing - see [MISS] lines.")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
