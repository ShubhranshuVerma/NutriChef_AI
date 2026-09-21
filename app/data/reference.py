"""Small, hand-curated reference tables committed to the repo (data/reference/)."""

from pathlib import Path

import pandas as pd

from app.core.config import PROJECT_ROOT
from app.data.recipenlg import LIST_COLUMNS, parse_list

REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "data" / "knowledge_base"



def _read(name: str, directory: Path = REFERENCE_DIR) -> pd.DataFrame:
    return pd.read_csv(directory / name, keep_default_na=False)


def load_allergen_keywords() -> pd.DataFrame:
    return _read("allergen_keywords.csv")


def load_food_group_keywords() -> pd.DataFrame:
    return _read("food_group_keywords.csv")


def load_keyword_exceptions() -> pd.DataFrame:
    return _read("keyword_exceptions.csv")


def load_diets() -> pd.DataFrame:
    df = _read("diets.csv")
    df["excluded_groups"] = df["excluded_groups"].map(
        lambda s: [g for g in s.split(";") if g] if s else []
    )
    return df


def load_prices() -> pd.DataFrame:
    df = _read("prices_inr.csv")
    df["price_inr"] = df["price_inr"].astype(float)
    df["grams_per_unit"] = df["grams_per_unit"].astype(float)
    return df


def load_curated_recipes() -> pd.DataFrame:
    df = _read("curated_indian_recipes.csv")
    for column in LIST_COLUMNS:
        df[column] = df[column].map(parse_list)
    return df


def knowledge_base_files() -> list[Path]:
    return sorted(KNOWLEDGE_BASE_DIR.glob("*.md"))
