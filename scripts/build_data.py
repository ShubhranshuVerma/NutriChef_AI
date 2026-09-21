"""Build every data file NutriChef needs, in order.

Run from the project root:
    python -m scripts.build_data                  # every step, in order
    python -m scripts.build_data nutrition tags   # only the steps you name

The steps, and what each one makes (all in data/processed/, git-ignored):
    usda       download USDA SR Legacy          -> usda_foods.csv
    recipenlg  sample the RecipeNLG csv         -> recipenlg_sample.csv
    foods      link catalog ingredients to USDA -> ingredient_foods.csv
    recipes    clean RecipeNLG + curated recipes -> recipes.jsonl
    nutrition  nutrition and cost per recipe    -> recipes_nutrition.jsonl
    tags       allergen, food-group, diet tags  -> recipes_tagged.jsonl  (the library)
    index      ChromaDB search index            -> chroma_db/

If the USDA download fails (network/firewall), download "SR Legacy - CSV" from
https://fdc.nal.usda.gov/download-datasets, save it as
data/raw/usda/FoodData_Central_sr_legacy_food_csv_2018-04.zip, and run again.
"""

import argparse
import shutil
import sys
import urllib.error
from collections import Counter

import pandas as pd

from app.agents import rag
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.data import recipenlg, recipes, reference, usda
from app.nutrition.calculator import INGREDIENT_FOODS_PATH, calculate_recipe, load_tables
from app.nutrition.checks import load_rules, nutrition_looks_wrong, tag_recipe
from app.nutrition.food_matcher import IngredientMatcher, load_catalog, resolve_usda
from app.services.planner import LIBRARY_PATH

MAX_KCAL_PER_SERVING = 2000  # anything above this is probably a parsing mistake
INDEX_BATCH_SIZE = 500


# ---------- the steps ----------

def step_usda(args):
    try:
        usda.download(force=args.force)
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"Download failed: {error}\n\n{__doc__}")
        return False
    table = usda.extract_foods()
    path = usda.save(table)
    print(f"Saved {len(table):,} foods -> {path}")
    return True


def step_recipenlg(args):
    try:
        path = recipenlg.csv_path()
    except recipenlg.RecipeNLGNotFoundError as error:
        print(error)
        return False
    recipenlg.validate_header(path)
    sample = recipenlg.sample(path, n=args.sample, seed=args.seed, source="Gathered")
    out = recipenlg.save_sample(sample)
    print(f"Saved {len(sample):,} rows -> {out}")
    return True


def step_foods(args):
    if not usda.OUTPUT_PATH.exists():
        print("USDA foods not found - run the 'usda' step first.")
        return False
    table = resolve_usda(load_catalog(), pd.read_csv(usda.OUTPUT_PATH))
    INGREDIENT_FOODS_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(INGREDIENT_FOODS_PATH, index=False)
    print(f"Saved {len(table)} ingredients -> {INGREDIENT_FOODS_PATH}")
    print(table["match_type"].value_counts().to_string())

    # 'fuzzy' used the closest USDA description, 'missing' needs a fix: correct
    # usda_description or set usda_fdc_id in data/reference/ingredient_catalog.csv.
    review = table[table["match_type"].isin(["fuzzy", "missing"])]
    for row in review.itertuples():
        print(f"  review [{row.match_type:7}] {row.ingredient_id:18} "
              f"{row.requested_description!r} -> {row.usda_description!r}")
    missing = int((table["match_type"] == "missing").sum())
    if missing:
        print(f"{missing} ingredients have no USDA match - they will count as unknown.")
    return True


def step_recipes(args):
    if not recipenlg.SAMPLE_PATH.exists():
        print("RecipeNLG sample not found - run the 'recipenlg' step first.")
        return False
    limit = args.limit or get_settings().recipenlg_subset_size
    matcher = IngredientMatcher()
    curated = recipes.records_from_curated(reference.load_curated_recipes(), matcher)
    # A few extra rows, so the limit is still reached after filtering.
    sample = recipenlg.load_sample().head(int(limit * 1.5))
    others = recipes.records_from_recipenlg(sample, matcher)
    cleaned, stats = recipes.clean(curated + others, max_recipenlg=limit)
    path = recipes.save(cleaned)

    df = recipes.load(path)
    print(f"Saved {len(df):,} recipes -> {path}")
    print(f"Cleaning: {stats}")
    print(f"Library-ready: {df['library_ready'].sum():,} / {len(df):,}")
    print("Most common unmapped ingredient names (candidates for the catalog):")
    for name, count in recipes.unmapped_names(cleaned, top=15):
        print(f"  {count:6}  {name}")
    return True


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


def step_nutrition(args):
    if not INGREDIENT_FOODS_PATH.exists() or not recipes.RECIPES_PATH.exists():
        print("Run the 'foods' and 'recipes' steps first.")
        return False
    tables = load_tables()
    table = pd.read_json(recipes.RECIPES_PATH, lines=True)
    df = pd.DataFrame([add_nutrition(row.to_dict(), tables) for _, row in table.iterrows()])
    recipes.NUTRITION_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_json(recipes.NUTRITION_PATH, orient="records", lines=True, force_ascii=False)
    print(f"Saved {len(df):,} recipes -> {recipes.NUTRITION_PATH}")
    print(df["nutrition_confidence"].value_counts().to_string())
    print(f"Library-ready: {df['library_ready'].sum():,}")
    return True


def step_tags(args):
    if not recipes.NUTRITION_PATH.exists():
        print("Run the 'nutrition' step first.")
        return False
    rules = load_rules()
    rows = []
    for _, row in pd.read_json(recipes.NUTRITION_PATH, lines=True).iterrows():
        recipe = tag_recipe(row.to_dict(), rules)
        if nutrition_looks_wrong(recipe):
            recipe["library_ready"] = False
            recipe["nutrition_confidence"] = "low"
        rows.append(recipe)

    df = pd.DataFrame(rows)
    LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_json(LIBRARY_PATH, orient="records", lines=True, force_ascii=False)
    print(f"Saved {len(df):,} tagged recipes -> {LIBRARY_PATH}")
    allergens = Counter(a for tags in df["allergens"] for a in tags)
    print("Recipes per allergen:", dict(allergens.most_common()))
    print(f"Library-ready: {df['library_ready'].sum():,}")
    return True


def step_index(args):
    if not LIBRARY_PATH.exists():
        print("Run the 'tags' step first.")
        return False
    directory = get_settings().chroma_dir
    if args.rebuild and directory.exists():
        shutil.rmtree(directory)
        print(f"Deleted the old index at {directory}")

    # The first run downloads the MiniLM embedding model (~90 MB).
    embeddings = rag.get_embeddings()
    guidance = rag.guidance_documents()
    add_in_batches(rag.open_collection(rag.GUIDANCE_COLLECTION, embeddings), guidance)
    print(f"Knowledge base: {len(guidance)} chunks")

    library = pd.read_json(LIBRARY_PATH, lines=True)
    library = library[library["library_ready"]].head(args.recipes).to_dict("records")
    documents = rag.recipe_documents(library)
    add_in_batches(rag.open_collection(rag.RECIPES_COLLECTION, embeddings), documents)
    print(f"Recipes: {len(documents):,} documents -> {directory}")

    print("Example search: 'high protein paneer dinner' (vegetarian, no soy)")
    for hit in rag.search_recipes("high protein paneer dinner", k=3, embeddings=embeddings,
                                  diet="vegetarian", avoid_allergens=["soy"]):
        print(f"  {hit['metadata']['title'][:50]}")
    return True


def add_in_batches(collection, documents):
    for start in range(0, len(documents), INDEX_BATCH_SIZE):
        collection.add_documents(documents[start:start + INDEX_BATCH_SIZE])


STEPS = {
    "usda": step_usda,
    "recipenlg": step_recipenlg,
    "foods": step_foods,
    "recipes": step_recipes,
    "nutrition": step_nutrition,
    "tags": step_tags,
    "index": step_index,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("steps", nargs="*", help="steps to run (default: all, in order)")
    parser.add_argument("--force", action="store_true", help="usda: download again")
    parser.add_argument("--sample", type=int, default=50_000, help="recipenlg: rows to sample")
    parser.add_argument("--seed", type=int, default=42, help="recipenlg: random seed")
    parser.add_argument("--limit", type=int, help="recipes: RecipeNLG recipes to keep "
                                                  "(default RECIPENLG_SUBSET_SIZE)")
    parser.add_argument("--recipes", type=int, default=2000, help="index: recipes to index")
    parser.add_argument("--rebuild", action="store_true", help="index: delete it first")
    args = parser.parse_args()
    for name in args.steps:
        if name not in STEPS:
            parser.error(f"unknown step {name!r} - choose from: {', '.join(STEPS)}")
    configure_logging()

    for name in args.steps or list(STEPS):
        print(f"\n===== {name} =====")
        if not STEPS[name](args):
            print(f"\nStopped at '{name}'. Fix the problem above and run it again.")
            return 1
    print("\nDone. Check everything with: python -m scripts.check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
