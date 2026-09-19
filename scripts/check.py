"""Is NutriChef ready to run? Settings, then every data file, in one place.

Run from the project root:
    python -m scripts.check              # offline checks
    python -m scripts.check --ping-llm   # also sends one tiny request to Gemini
"""

import argparse
import os
import sys

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")  # silence MLflow's import banner

from app.core.config import PROJECT_ROOT, get_settings
from app.datasets import recipenlg, reference, usda
from app.nutrition.food_matcher import load_catalog

OK, MISSING, WARN = "[ OK ]", "[MISS]", "[WARN]"


def check_settings() -> bool:
    """Config and secrets. Never prints the key itself."""
    if (PROJECT_ROOT / ".env").exists():
        print(f"  {OK} .env found")
    else:
        print(f"  {WARN} .env not found - run: cp .env.example .env")

    try:
        settings = get_settings()
    except Exception as exc:
        print(f"  {MISSING} settings invalid: {exc}")
        return False

    print(f"  {OK} settings loaded (env={settings.environment}, model={settings.gemini_model})")
    if settings.has_llm_key:
        print(f"  {OK} GOOGLE_API_KEY is set")
    else:
        print(f"  {WARN} GOOGLE_API_KEY is empty - the LLM features will not work")
    if settings.jwt_secret_key.get_secret_value() == "change-me":
        print(f"  {WARN} JWT_SECRET_KEY is still the placeholder - change it before deploying")
    return True


def ping_llm() -> bool:
    """One small real request, to prove the key and the model name work."""
    from app.agents.agents import answer_text
    from app.core.llm import get_llm

    try:
        reply = answer_text(get_llm(temperature=0).invoke("Reply with exactly one word: OK"))
    except Exception as exc:
        print(f"  {MISSING} Gemini call failed: {type(exc).__name__}: {str(exc)[:200]}")
        return False
    print(f"  {OK} Gemini replied: {reply.strip()!r}")
    return True


def check_reference() -> None:
    """The small committed files. If these are missing, the clone is broken."""
    loaders = {
        "allergen keywords": reference.load_allergen_keywords,
        "food group keywords": reference.load_food_group_keywords,
        "keyword exceptions": reference.load_keyword_exceptions,
        "diets": reference.load_diets,
        "prices (INR)": reference.load_prices,
        "curated recipes": reference.load_curated_recipes,
        "ingredient catalog": load_catalog,
    }
    for name, loader in loaders.items():
        print(f"  {OK} {name:<22} {len(loader()):>5} rows")
    print(f"  {OK} {'knowledge base docs':<22} {len(reference.knowledge_base_files()):>5} files")


def check_generated() -> bool:
    """The git-ignored files, each with the command that rebuilds it."""
    from app.ml.ranker import MODEL_PATH
    from app.processing.recipes import RECIPES_PATH
    from app.services.planner import LIBRARY_PATH
    from scripts.build_ingredient_foods import OUTPUT_PATH as FOODS_MAP
    from scripts.compute_nutrition import OUTPUT_PATH as NUTRITION_PATH
    from scripts.simulate_users import INTERACTIONS_PATH

    steps = [
        ("USDA foods", usda.OUTPUT_PATH, "scripts.download_usda"),
        ("RecipeNLG csv", get_settings().recipenlg_csv_path, "download it, set RECIPENLG_CSV_PATH"),
        ("RecipeNLG sample", recipenlg.SAMPLE_PATH, "scripts.sample_recipenlg"),
        ("ingredient -> USDA", FOODS_MAP, "scripts.build_ingredient_foods"),
        ("processed recipes", RECIPES_PATH, "scripts.process_recipes"),
        ("recipes + nutrition", NUTRITION_PATH, "scripts.compute_nutrition"),
        ("tagged recipes", LIBRARY_PATH, "scripts.tag_recipes"),
        ("simulated feedback", INTERACTIONS_PATH, "scripts.simulate_users"),
        ("ranking model", MODEL_PATH, "scripts.train_ranker"),
        ("search index", get_settings().chroma_dir, "scripts.build_index"),
    ]
    ready = True
    for name, path, command in steps:
        if path.exists():
            print(f"  {OK} {name:<22} ({path.name})")
        else:
            ready = False
            how = f"python -m {command}" if command.startswith("scripts.") else command
            print(f"  {MISSING} {name:<22} {how}")
    return ready


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ping-llm", action="store_true", help="send one small request to Gemini")
    args = parser.parse_args()

    print("\nSettings:")
    ok = check_settings()
    if args.ping_llm:
        ok = ping_llm() and ok

    print("\nReference data (committed):")
    check_reference()

    print("\nGenerated data (git-ignored):")
    ok = check_generated() and ok

    print("\nEverything is ready." if ok else "\nSomething is missing - see the lines above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
