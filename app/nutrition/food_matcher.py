"""Map ingredient names to NutriChef catalog ids, and catalog ids to USDA foods.

Matching is deterministic: the name is normalised, then the longest alias
found as whole words wins ("brown sugar" beats "sugar", "eggplant" never
matches "egg").
"""

import difflib
import re

import pandas as pd

from app.data.reference import REFERENCE_DIR

CATALOG_PATH = REFERENCE_DIR / "ingredient_catalog.csv"
NUTRIENT_COLUMNS = ["kcal", "protein_g", "carbs_g", "fat_g", "fiber_g"]
MAX_ALIAS_WORDS = 5

# Words that describe preparation or size rather than the food itself.
DESCRIPTOR_WORDS = {
    "fresh", "freshly", "frozen", "dried", "dry", "raw", "cooked", "canned", "large", "small",
    "medium", "big", "chopped", "finely", "coarsely", "roughly", "thinly", "diced", "minced",
    "sliced", "grated", "shredded", "crushed", "ground", "whole", "halved", "quartered",
    "peeled", "seeded", "cubed", "mashed", "softened", "melted", "beaten", "packed", "firmly",
    "lightly", "loosely", "sifted", "boiled", "hard-boiled", "soaked", "rinsed", "drained",
    "optional", "plus", "extra", "more", "about", "approx", "approximately", "good", "quality",
    "organic", "ripe", "room", "temperature", "cold", "warm", "hot", "boiling", "divided",
    "taste", "to", "for", "garnish", "and", "or", "a", "an", "the", "of", "few", "some",
    "heaping", "level", "scant", "generous", "bite", "size", "bite-size", "pinch", "dash",
    "handful", "cup", "cups", "tbsp", "tsp", "g", "ml",
}


def normalize_name(text: str) -> str:
    """Lower-case, drop brackets, punctuation and descriptor words."""
    text = text.lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z\s\-']", " ", text)
    words = [w.strip("-'") for w in text.split()]
    words = [w for w in words if w and w not in DESCRIPTOR_WORDS]
    return " ".join(words)


def _tokens(text: str) -> list[str]:
    return re.sub(r"[^a-z\s\-']", " ", text.lower()).split()


def load_catalog() -> pd.DataFrame:
    df = pd.read_csv(CATALOG_PATH, keep_default_na=False)
    df["grams_per_piece"] = df["grams_per_piece"].astype(float)
    df["density_g_ml"] = df["density_g_ml"].astype(float)
    return df


class IngredientMatcher:
    """Find the catalog ingredient mentioned in a free-text name."""

    def __init__(self, catalog: pd.DataFrame | None = None):
        self.catalog = load_catalog() if catalog is None else catalog
        self.alias_to_id: dict[tuple[str, ...], str] = {}
        for row in self.catalog.itertuples():
            names = [row.name, *[a for a in row.aliases.split(";") if a.strip()]]
            for alias in names:
                key = tuple(_tokens(alias))
                if key:
                    self.alias_to_id.setdefault(key, row.ingredient_id)

    def _search(self, words: list[str]) -> str | None:
        best: tuple[int, int, str] | None = None  # (length, -position, id)
        for size in range(min(MAX_ALIAS_WORDS, len(words)), 0, -1):
            for start in range(len(words) - size + 1):
                found = self.alias_to_id.get(tuple(words[start : start + size]))
                if found:
                    candidate = (size, -start, found)
                    if best is None or candidate > best:
                        best = candidate
            if best:
                return best[2]
        return None

    def match(self, text: str) -> str | None:
        """Return the ingredient_id for a name like 'firmly packed brown sugar'."""
        if not text:
            return None
        # Try the raw words first (keeps phrases such as "ground beef"), then the cleaned ones.
        for words in (_tokens(text), normalize_name(text).split()):
            found = self._search(words)
            if found:
                return found
        singular = [w[:-1] if w.endswith("s") and len(w) > 3 else w for w in normalize_name(text).split()]
        return self._search(singular)


def pick_ner_name(line: str, ner: list[str]) -> str | None:
    """RecipeNLG gives a list of food entities per recipe; return the longest one in this line."""
    lowered = f" {' '.join(_tokens(line))} "
    hits = [e for e in ner if e and f" {' '.join(_tokens(e))} " in lowered]
    return max(hits, key=len) if hits else None



def _clean_description(text: str) -> str:
    """'Oats (Includes foods for USDA's Food Distribution Program)' -> 'oats'."""
    return re.sub(r"\s*\([^)]*\)", "", text).strip().lower()


def _find_food(requested: str, foods: pd.DataFrame, cleaned: pd.Series) -> tuple[int | None, str]:
    """Return (row index, match_type) for a requested USDA description."""
    target = requested.strip().lower()
    exact = foods.index[foods["description"].str.lower() == target]
    if len(exact):
        return exact[0], "exact"
    # Same text once bracketed notes are removed, e.g. "(Includes foods for ... Program)"
    same = cleaned.index[cleaned == target]
    if len(same):
        return same[0], "exact"
    # Longer description that starts with the requested one; take the shortest.
    longer = cleaned[cleaned.str.startswith(target + ",")]
    if len(longer):
        return longer.str.len().idxmin(), "prefix"
    head = target.split(",")[0].strip()
    pool = cleaned[cleaned.str.startswith(head)]
    # Same first word: accept a looser match. Otherwise demand a very close one.
    close = difflib.get_close_matches(target, pool.tolist(), n=1, cutoff=0.6)
    if not close:
        close = difflib.get_close_matches(target, cleaned.tolist(), n=1, cutoff=0.85)
    if close:
        return cleaned.index[cleaned == close[0]][0], "fuzzy"
    return None, "missing"


def resolve_usda(catalog: pd.DataFrame, foods: pd.DataFrame) -> pd.DataFrame:
    """Attach USDA nutrients (per 100 g) to every catalog ingredient.

    match_type:
      manual     - fdc_id given in the catalog's `usda_fdc_id` column
      exact      - description matches (ignoring bracketed notes)
      prefix     - a more specific USDA description that starts with the requested one
      fuzzy      - closest description; PLEASE REVIEW
      negligible - no nutrition by design (water, curry leaves, cooking spray)
      missing    - nothing suitable found; fix the catalog
    """
    foods = foods.reset_index(drop=True)
    cleaned = foods["description"].map(_clean_description)
    by_fdc = {int(v): i for i, v in foods["fdc_id"].items()}
    rows = []
    for item in catalog.itertuples():
        record = {"ingredient_id": item.ingredient_id, "nutrition_source": item.nutrition_source,
                  "requested_description": item.usda_description}
        if item.nutrition_source == "negligible":
            record.update({"match_type": "negligible", "fdc_id": None, "usda_description": ""})
            record.update(dict.fromkeys(NUTRIENT_COLUMNS, 0.0))
            rows.append(record)
            continue

        manual_id = str(getattr(item, "usda_fdc_id", "") or "").strip()
        if manual_id:
            index = by_fdc.get(int(float(manual_id)))
            match_type = "manual" if index is not None else "missing"
        else:
            index, match_type = _find_food(item.usda_description, foods, cleaned)

        if index is None:
            record.update({"match_type": "missing", "fdc_id": None, "usda_description": ""})
            record.update(dict.fromkeys(NUTRIENT_COLUMNS, None))
        else:
            food = foods.loc[index]
            record.update({"match_type": match_type, "fdc_id": int(food["fdc_id"]),
                           "usda_description": food["description"]})
            record.update({c: food[c] for c in NUTRIENT_COLUMNS})
        rows.append(record)
    return pd.DataFrame(rows)
