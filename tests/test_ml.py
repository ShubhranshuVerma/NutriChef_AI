"""The ranking model: how it is measured, and how it takes over from the rules."""

import pytest

from app.ml import features, ranker
from app.ml.metrics import hit_rate_at_k, ndcg_at_k, precision_at_k, recall_at_k

USER = {"diet": "vegetarian", "cuisine": "indian", "kcal_target": 450, "protein_target_g": 20,
        "budget_per_meal_inr": 60, "max_cook_minutes": 30, "inventory": ["paneer", "onion"],
        "liked_ingredients": ["paneer"]}
GOOD = {"recipe_id": "r1", "kcal": 450, "protein_g": 25, "cost_per_serving_inr": 40,
        "cook_minutes": 20, "cuisine_group": "indian", "suitable_diets": ["vegetarian"],
        "ingredient_ids": ["paneer", "onion"], "origin": "curated", "n_ingredients": 8}
POOR = {"recipe_id": "r2", "kcal": 900, "protein_g": 5, "cost_per_serving_inr": 200,
        "cook_minutes": 90, "cuisine_group": "italian", "suitable_diets": ["non_vegetarian"],
        "ingredient_ids": ["pasta"], "origin": "recipenlg", "n_ingredients": 12}

RECOMMENDED = ["a", "b", "c", "d", "e"]
LIKED = {"b", "e", "z"}


# ---------- measuring a ranking ----------

def test_precision_recall_and_hit_rate():
    assert precision_at_k(RECOMMENDED, LIKED, k=5) == 2 / 5
    assert recall_at_k(RECOMMENDED, LIKED, k=5) == 2 / 3
    assert hit_rate_at_k(RECOMMENDED, LIKED, k=5) == 1.0
    assert hit_rate_at_k(RECOMMENDED, LIKED, k=1) == 0.0


def test_ndcg_rewards_putting_liked_recipes_first():
    assert ndcg_at_k(["b", "e", "x"], {"b", "e"}, k=3) == 1.0
    assert ndcg_at_k(["x", "b", "e"], {"b", "e"}, k=3) < 1.0


# ---------- scoring ----------

def test_features_are_between_0_and_1():
    values = features.build_features(USER, GOOD)
    assert set(values) == set(features.FEATURE_NAMES)
    assert all(0 <= v <= 1 for v in values.values())


def test_a_good_match_scores_higher_than_a_poor_one():
    assert ranker.rule_score(USER, GOOD) > ranker.rule_score(USER, POOR)


class AlwaysNo:
    """A stand-in model that is sure the person will not like anything."""

    def predict_proba(self, rows):
        return [[1.0, 0.0]]


def test_a_new_user_gets_the_rules_and_a_regular_gets_the_model():
    new_user = ranker.score_recipe(USER, GOOD, model=AlwaysNo(), n_interactions=0)
    regular = ranker.score_recipe(USER, GOOD, model=AlwaysNo(), n_interactions=20)
    assert new_user == pytest.approx(ranker.rule_score(USER, GOOD))
    assert regular == 0.0                                  # fully trusts the model


def test_no_trained_model_yet_is_fine(tmp_path):
    assert ranker.load_model(tmp_path / "missing.joblib") == (None, None)


def test_a_model_file_that_cannot_be_read_falls_back_to_the_rules(tmp_path):
    """A model saved by another scikit-learn version must not break every meal plan."""
    broken = tmp_path / "ranker.joblib"
    broken.write_bytes(b"not a model")
    assert ranker.load_model(broken) == (None, None)
