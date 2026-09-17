"""Clean the RecipeNLG sample + curated recipes into data/processed/recipes.jsonl.

Run from the project root (after scripts.sample_recipenlg):
    python -m scripts.process_recipes              # keeps RECIPENLG_SUBSET_SIZE RecipeNLG recipes
    python -m scripts.process_recipes --limit 20000
"""

import argparse
import sys
import time

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.datasets import recipenlg, reference
from app.nutrition.food_matcher import IngredientMatcher
from app.processing import recipes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="max RecipeNLG recipes to keep (default: RECIPENLG_SUBSET_SIZE)")
    args = parser.parse_args()
    configure_logging()
    limit = args.limit or get_settings().recipenlg_subset_size

    if not recipenlg.SAMPLE_PATH.exists():
        print("RecipeNLG sample not found - run: python -m scripts.sample_recipenlg")
        return 1

    started = time.perf_counter()
    matcher = IngredientMatcher()
    curated = recipes.records_from_curated(reference.load_curated_recipes(), matcher)
    # Process a few extra rows so that the limit is still reached after filtering.
    sample = recipenlg.load_sample().head(int(limit * 1.5))
    others = recipes.records_from_recipenlg(sample, matcher)
    cleaned, stats = recipes.clean(curated + others, max_recipenlg=limit)
    path = recipes.save(cleaned)

    df = recipes.load(path)
    print(f"Saved {len(df):,} recipes -> {path} ({time.perf_counter() - started:.0f}s)")
    print(f"Cleaning: {stats}")
    print(f"\nBy origin:\n{df['origin'].value_counts().to_string()}")
    print(f"\nLibrary-ready (>= {recipes.LIBRARY_MIN_MAPPED:.0%} mapped, quantities parsed): "
          f"{df['library_ready'].sum():,} / {len(df):,}")
    print(f"Mapped ratio: median {df['mapped_ratio'].median():.2f}, "
          f"mean {df['mapped_ratio'].mean():.2f}")
    print(f"\nCuisine:\n{df['cuisine'].value_counts().to_string()}")
    print(f"\nMeal type:\n{df['meal_type'].value_counts().to_string()}")
    print("\nTop unmapped ingredient names (candidates for the catalog):")
    for name, count in recipes.unmapped_names(cleaned, top=25):
        print(f"  {count:6}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
