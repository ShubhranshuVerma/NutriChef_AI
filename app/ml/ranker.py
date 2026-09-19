"""Score and sort recipes for a user.

- With a trained model: probability that the user will like the recipe.
- New user (few interactions): a simple rule score, blended with the model.
"""

import json

import joblib
import pandas as pd

from app.core.config import PROJECT_ROOT
from app.ml.features import FEATURE_NAMES, build_features, feature_row

MODEL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "ranker.joblib"
MODEL_INFO_PATH = PROJECT_ROOT / "ml" / "artifacts" / "ranker_info.json"
COLD_START_INTERACTIONS = 5  # below this we lean on the rule score

RULE_WEIGHTS = {
    "diet_match": 3.0, "calorie_fit": 2.0, "protein_fit": 2.0, "cost_fit": 1.0,
    "time_fit": 1.0, "cuisine_match": 1.5, "inventory_use": 2.0, "ingredient_overlap": 1.0,
}


def rule_score(user, recipe):
    """Simple weighted score, used when we have no model or no history."""
    values = build_features(user, recipe)
    total = sum(RULE_WEIGHTS[name] * values[name] for name in RULE_WEIGHTS)
    return total / sum(RULE_WEIGHTS.values())


def load_model(path=MODEL_PATH):
    """Return (model, info) or (None, None) if no model has been trained yet."""
    if not path.exists():
        return None, None
    info = json.loads(MODEL_INFO_PATH.read_text()) if MODEL_INFO_PATH.exists() else {}
    return joblib.load(path), info


def score_recipe(user, recipe, model=None, n_interactions=0):
    """Score between 0 and 1. Mixes the rule score in for users with little history."""
    rule = rule_score(user, recipe)
    if model is None:
        return rule
    # A DataFrame with the same column names the model was trained on, so sklearn
    # does not warn about missing feature names.
    row = pd.DataFrame([feature_row(user, recipe)], columns=FEATURE_NAMES)
    probability = model.predict_proba(row)[0][1]
    weight = min(n_interactions, COLD_START_INTERACTIONS) / COLD_START_INTERACTIONS
    return weight * probability + (1 - weight) * rule


