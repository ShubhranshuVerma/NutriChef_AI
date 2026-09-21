"""Turn raw recipes (RecipeNLG sample + curated Indian recipes) into one clean table.

Each recipe gets parsed ingredients linked to catalog ids, basic quality
checks, de-duplication and the static features from `features.py`.
Output: data/processed/recipes.jsonl (one JSON object per line).
"""

import hashlib
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from app.core.config import PROJECT_ROOT
from app.core.logging import get_logger
from app.nutrition.food_matcher import IngredientMatcher, normalize_name, pick_ner_name
from app.nutrition.parsing import parse_ingredient
from app.data import features

log = get_logger(__name__)

RECIPES_PATH = PROJECT_ROOT / "data" / "processed" / "recipes.jsonl"
NUTRITION_PATH = PROJECT_ROOT / "data" / "processed" / "recipes_nutrition.jsonl"
MIN_INGREDIENTS, MAX_INGREDIENTS = 3, 20
LIBRARY_MIN_MAPPED = 0.9  # share of ingredients that must be linked to the catalog


def _recipe_id(prefix: str, title: str, link: str) -> str:
    digest = hashlib.sha1(f"{title}|{link}".encode(), usedforsecurity=False).hexdigest()[:12]
    return f"{prefix}_{digest}"


def parse_ingredient_lines(lines: list[str], matcher: IngredientMatcher,
                           ner: list[str] | None = None) -> list[dict]:
    parsed = []
    for line in lines:
        item = parse_ingredient(line)
        ingredient_id = matcher.match(item.name)
        if ingredient_id is None and ner:
            entity = pick_ner_name(line, ner)
            ingredient_id = matcher.match(entity) if entity else None
        parsed.append({
            "raw": item.raw, "quantity": item.quantity, "unit": item.unit,
            "name": item.name, "note": item.note, "ingredient_id": ingredient_id,
        })
    return parsed


def build_record(title: str, ingredients: list[str], directions: list[str], *, origin: str,
                 link: str, matcher: IngredientMatcher, ner: list[str] | None = None,
                 extra: dict | None = None) -> dict:
    title = re.sub(r"\s+", " ", str(title)).strip()
    directions = [d.strip() for d in directions if d and d.strip()]
    parsed = parse_ingredient_lines(ingredients, matcher, ner)
    ids = [p["ingredient_id"] for p in parsed if p["ingredient_id"]]
    n = len(parsed)
    record = {
        "recipe_id": _recipe_id("cur" if origin == "curated" else "rnlg", title, link),
        "title": title,
        "origin": origin,
        "source_url": link,
        "ingredients": parsed,
        "ingredient_ids": sorted(set(ids)),
        "directions": directions,
        "n_ingredients": n,
        "n_steps": len(directions),
        "mapped_ratio": round(len(ids) / n, 3) if n else 0.0,
        "quantities_parsed": all(p["quantity"] is not None for p in parsed),
        "cuisine": None, "meal_type": None, "diet": None, "cook_minutes": None, "servings": None,
    }
    record.update(extra or {})
    record["cuisine"] = record["cuisine"] or features.guess_cuisine(title, ids)
    record["meal_type"] = record["meal_type"] or features.guess_meal_type(title)
    record["cook_minutes"] = record["cook_minutes"] or features.estimate_minutes(directions)
    record["difficulty"] = features.difficulty(n, len(directions))
    record["cuisine_group"] = features.cuisine_group(record["cuisine"])
    record["course"] = features.course(record["meal_type"])
    record["library_ready"] = bool(
        record["mapped_ratio"] >= LIBRARY_MIN_MAPPED and record["quantities_parsed"]
    )
    return record


def records_from_recipenlg(df: pd.DataFrame, matcher: IngredientMatcher) -> list[dict]:
    return [
        build_record(row.title, row.ingredients, row.directions, origin="recipenlg",
                     link=str(row.link), matcher=matcher, ner=row.NER)
        for row in df.itertuples()
    ]


def records_from_curated(df: pd.DataFrame, matcher: IngredientMatcher) -> list[dict]:
    return [
        build_record(
            row.title, row.ingredients, row.directions, origin="curated", link="",
            matcher=matcher, ner=row.NER,
            extra={"cuisine": row.cuisine, "meal_type": row.meal_type, "diet": row.diet,
                   "cook_minutes": int(row.cook_minutes), "servings": int(row.servings)},
        )
        for row in df.itertuples()
    ]


def is_valid(record: dict) -> bool:
    return (
        bool(record["title"])
        and MIN_INGREDIENTS <= record["n_ingredients"] <= MAX_INGREDIENTS
        and record["n_steps"] >= 1
    )


def deduplicate(records: list[dict]) -> list[dict]:
    """Keep the first recipe per (normalised title, ingredient set). Curated recipes go first."""
    seen, kept = set(), []
    for record in sorted(records, key=lambda r: r["origin"] != "curated"):
        key = (normalize_name(record["title"]), tuple(record["ingredient_ids"]))
        if key not in seen:
            seen.add(key)
            kept.append(record)
    return kept


def clean(records: list[dict], max_recipenlg: int | None = None) -> tuple[list[dict], dict]:
    """Filter invalid rows, de-duplicate and cap the number of RecipeNLG recipes."""
    valid = [r for r in records if is_valid(r)]
    unique = deduplicate(valid)
    duplicates = len(valid) - len(unique)
    if max_recipenlg is not None:
        curated = [r for r in unique if r["origin"] == "curated"]
        others = [r for r in unique if r["origin"] != "curated"][:max_recipenlg]
        unique = curated + others
    stats = {
        "input": len(records),
        "invalid": len(records) - len(valid),
        "duplicates": duplicates,
        "output": len(unique),
    }
    return unique, stats


def unmapped_names(records: list[dict], top: int = 30) -> list[tuple[str, int]]:
    """Most common ingredient names that are not in the catalog yet."""
    counter = Counter(
        normalize_name(p["name"]) for r in records for p in r["ingredients"] if not p["ingredient_id"]
    )
    counter.pop("", None)
    return counter.most_common(top)


def save(records: list[dict], path: Path = RECIPES_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_json(path, orient="records", lines=True, force_ascii=False)
    return path


def load(path: Path = RECIPES_PATH) -> pd.DataFrame:
    return pd.read_json(path, orient="records", lines=True)
