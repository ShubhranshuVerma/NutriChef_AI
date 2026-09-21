"""RecipeNLG - read, profile and sample the ~2 GB CSV without loading it all.

Terms: non-commercial research and educational use only. Never commit the data.
"""

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.core.config import PROJECT_ROOT, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

EXPECTED_COLUMNS = ["title", "ingredients", "directions", "link", "source", "NER"]
LIST_COLUMNS = ["ingredients", "directions", "NER"]
SAMPLE_PATH = PROJECT_ROOT / "data" / "processed" / "recipenlg_sample.csv"


class RecipeNLGNotFoundError(FileNotFoundError):
    pass


def csv_path() -> Path:
    path = get_settings().recipenlg_csv_path
    if not path.exists():
        raise RecipeNLGNotFoundError(
            f"RecipeNLG CSV not found at {path}. Download it (see docs/data_sources.md) "
            "and set RECIPENLG_CSV_PATH in .env if it lives elsewhere."
        )
    return path


def validate_header(path: Path) -> list[str]:
    """Check that the file has the RecipeNLG columns. Returns the header."""
    header = pd.read_csv(path, nrows=0).columns.tolist()
    missing = [c for c in EXPECTED_COLUMNS if c not in header]
    if missing:
        raise ValueError(f"{path.name} is missing RecipeNLG columns: {missing}")
    return header


def parse_list(value) -> list[str]:
    """RecipeNLG stores lists as JSON text, e.g. '["1 c. sugar", "2 eggs"]'."""
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return []
    return [str(item).strip() for item in parsed] if isinstance(parsed, list) else []


def profile(path: Path, chunksize: int = 200_000) -> dict:
    """Count rows and rows per `source` with a streaming pass."""
    total, by_source = 0, {}
    for chunk in pd.read_csv(path, usecols=["source"], chunksize=chunksize):
        total += len(chunk)
        for source, count in chunk["source"].value_counts().items():
            by_source[source] = by_source.get(source, 0) + int(count)
    return {"rows": total, "by_source": by_source}


def sample(
    path: Path,
    n: int,
    seed: int = 42,
    source: str | None = "Gathered",
    chunksize: int = 100_000,
) -> pd.DataFrame:
    """Reproducible random sample of `n` rows, read chunk by chunk.

    Each row gets a random key from a seeded generator; the n smallest keys
    across all chunks are kept. Same file + seed + chunksize -> same sample.
    `source="Gathered"` keeps the rows RecipeNLG collected itself (the rest
    come from Recipe1M+, which has its own terms). Use source=None for all rows.
    """
    validate_header(path)
    rng = np.random.default_rng(seed)
    best: pd.DataFrame | None = None
    for chunk in pd.read_csv(path, usecols=EXPECTED_COLUMNS, chunksize=chunksize):
        keys = rng.random(len(chunk))  # drawn for every row so results don't depend on filtering
        chunk = chunk.assign(_key=keys)
        if source is not None:
            chunk = chunk[chunk["source"] == source]
        best = chunk if best is None else pd.concat([best, chunk])
        if len(best) > n:
            best = best.nsmallest(n, "_key")
    if best is None or best.empty:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)
    return best.sort_values("_key").drop(columns="_key").reset_index(drop=True)


def save_sample(df: pd.DataFrame, path: Path = SAMPLE_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def load_sample(path: Path = SAMPLE_PATH) -> pd.DataFrame:
    """Load a saved sample with list columns parsed into Python lists."""
    df = pd.read_csv(path)
    for column in LIST_COLUMNS:
        df[column] = df[column].map(parse_list)
    return df
