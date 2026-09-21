"""Score and sort recipes for a user.

- With a trained model: probability that the user will like the recipe.
- New user (few interactions): a simple rule score, blended with the model.
"""

import json

import joblib
import pandas as pd

from app.core.config import PROJECT_ROOT
from app.core.logging import get_logger
from app.ml.features import FEATURE_NAMES, build_features, feature_row

log = get_logger(__name__)

MODEL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "ranker.joblib"
MODEL_INFO_PATH = PROJECT_ROOT / "ml" / "artifacts" / "ranker_info.json"
# The simulated practice data the model is trained on (scripts/train_ranker.py).
USERS_PATH = PROJECT_ROOT / "data" / "interactions" / "users.csv"
INTERACTIONS_PATH = PROJECT_ROOT / "data" / "interactions" / "interactions.csv"
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
    try:
        model = joblib.load(path)
    except Exception as error:
        # A model saved by a different scikit-learn version often cannot be read back.
        # Plans still work on the rule score; retrain to use the model again.
        log.warning("could not load the ranking model (%s: %s) - using the rule score. "
                    "Run: python -m scripts.train_ranker", type(error).__name__, error)
        return None, None
    info = json.loads(MODEL_INFO_PATH.read_text()) if MODEL_INFO_PATH.exists() else {}
    return model, info


def score_recipe(user, recipe, model=None, n_interactions=0):
    """Score between 0 and 1. Mixes the rule score in for users with little history."""
    rule = rule_score(user, recipe)
    weight = min(n_interactions, COLD_START_INTERACTIONS) / COLD_START_INTERACTIONS
    if model is None or weight == 0:
        # With no history the model's answer is multiplied by zero, so do not ask
        # for it: a DataFrame and a predict_proba per recipe cost ~1 ms each, and
        # a meal plan scores ~1,200 recipes. That was 1.2 s of every plan, spent
        # computing numbers that were then thrown away.
        return rule
    # A DataFrame with the same column names the model was trained on, so sklearn
    # does not warn about missing feature names.
    row = pd.DataFrame([feature_row(user, recipe)], columns=FEATURE_NAMES)
    probability = model.predict_proba(row)[0][1]
    return weight * probability + (1 - weight) * rule


