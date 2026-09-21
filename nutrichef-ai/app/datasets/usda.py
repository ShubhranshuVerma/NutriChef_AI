"""USDA FoodData Central (SR Legacy) - download and extract nutrient values.

SR Legacy is public domain (CC0) and no longer changes, so it is a stable
source for per-100 g nutrient values of common foods.

Output: one row per food with the five nutrients NutriChef needs.
"""

import io
import shutil
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from app.core.config import PROJECT_ROOT
from app.core.logging import get_logger

log = get_logger(__name__)

SR_LEGACY_URL = (
    "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip"
)
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "usda"
ZIP_PATH = RAW_DIR / "FoodData_Central_sr_legacy_food_csv_2018-04.zip"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "usda_foods.csv"

# FoodData Central nutrient ids -> our column names (all values are per 100 g)
NUTRIENTS = {
    1008: "kcal",  # Energy (KCAL)
    1003: "protein_g",  # Protein
    1005: "carbs_g",  # Carbohydrate, by difference
    1004: "fat_g",  # Total lipid (fat)
    1079: "fiber_g",  # Fiber, total dietary
}
OUTPUT_COLUMNS = ["fdc_id", "description", "category", *NUTRIENTS.values()]


def download(url: str = SR_LEGACY_URL, dest: Path = ZIP_PATH, force: bool = False) -> Path:
    """Download the zip once. Skips the download if the file already exists."""
    if dest.exists() and not force:
        log.info("Already downloaded: %s", dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    log.info("Downloading %s", url)
    request = urllib.request.Request(url, headers={"User-Agent": "NutriChef-AI/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response, open(tmp, "wb") as out:
        shutil.copyfileobj(response, out)
    tmp.rename(dest)
    log.info("Saved %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
    return dest


def _read_csv_from_zip(zf: zipfile.ZipFile, filename: str, **kwargs) -> pd.DataFrame:
    """Read a CSV inside the zip regardless of the folder it sits in."""
    matches = [n for n in zf.namelist() if n.rsplit("/", 1)[-1] == filename]
    if not matches:
        raise FileNotFoundError(f"{filename} not found inside the USDA zip")
    with zf.open(matches[0]) as fh:
        return pd.read_csv(io.TextIOWrapper(fh, encoding="utf-8"), **kwargs)


def extract_foods(zip_path: Path = ZIP_PATH) -> pd.DataFrame:
    """Build a tidy table: fdc_id, description, category, kcal, protein_g, carbs_g, fat_g, fiber_g."""
    with zipfile.ZipFile(zip_path) as zf:
        foods = _read_csv_from_zip(
            zf, "food.csv", usecols=["fdc_id", "description", "food_category_id"]
        )
        categories = _read_csv_from_zip(zf, "food_category.csv", usecols=["id", "description"])
        amounts = _read_csv_from_zip(
            zf, "food_nutrient.csv", usecols=["fdc_id", "nutrient_id", "amount"]
        )

    amounts = amounts[amounts["nutrient_id"].isin(NUTRIENTS)]
    wide = (
        amounts.pivot_table(index="fdc_id", columns="nutrient_id", values="amount", aggfunc="first")
        .rename(columns=NUTRIENTS)
        .reset_index()
    )
    for column in NUTRIENTS.values():  # a nutrient may be missing entirely in small files
        if column not in wide:
            wide[column] = float("nan")

    categories = categories.rename(columns={"id": "food_category_id", "description": "category"})
    table = foods.merge(categories, on="food_category_id", how="left").merge(
        wide, on="fdc_id", how="inner"
    )
    table = table.dropna(subset=["kcal"])  # energy is required
    table["description"] = table["description"].str.strip()
    return table[OUTPUT_COLUMNS].sort_values("fdc_id").reset_index(drop=True)


def save(table: pd.DataFrame, path: Path = OUTPUT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)
    return path
