import pytest

from app.ml import features, ranker

USER = {"diet": "vegetarian", "cuisine": "indian", "kcal_target": 450, "protein_target_g": 20,
        "budget_per_meal_inr": 60, "max_cook_minutes": 30, "inventory": ["paneer", "onion"],
        "liked_ingredients": ["paneer"]}

GOOD = {"recipe_id": "r1", "kcal": 450, "protein_g": 25, "cost_per_serving_inr": 40,
        "cook_minutes": 20, "cuisine_group": "indian", "suitable_diets": ["vegetarian"],
        "ingredient_ids": ["paneer", "onion"], "origin": "curated", "n_ingredients": 8}
POOR = {"recipe_id": "r2", "kcal": 900, "protein_g": 5, "cost_per_serving_inr": 200,
        "cook_minutes": 90, "cuisine_group": "italian", "suitable_diets": ["non_vegetarian"],
        "ingredient_ids": ["pasta"], "origin": "recipenlg", "n_ingredients": 12}


def test_features_are_between_0_and_1():
    values = features.build_features(USER, GOOD)
    assert set(values) == set(features.FEATURE_NAMES)
    assert all(0 <= v <= 1 for v in values.values())


def test_good_recipe_scores_higher_than_poor_one():
    assert ranker.rule_score(USER, GOOD) > ranker.rule_score(USER, POOR)


def test_rank_recipes_sorts_and_limits():
    ranked = ranker.rank_recipes(USER, [POOR, GOOD], top_k=1)
    assert [r["recipe_id"] for r in ranked] == ["r1"]
    assert 0 <= ranked[0]["score"] <= 1


class FakeModel:
    """Always says 'likes the second recipe', to test the cold-start blend."""

    def predict_proba(self, rows):
        return [[0.0, 1.0] if row[0] < 0.5 else [1.0, 0.0] for row in rows]


def test_cold_start_uses_rules_then_shifts_to_the_model():
    new_user = ranker.score_recipe(USER, GOOD, model=FakeModel(), n_interactions=0)
    experienced = ranker.score_recipe(USER, GOOD, model=FakeModel(), n_interactions=20)
    assert new_user == pytest.approx(ranker.rule_score(USER, GOOD))
    assert experienced == 0.0  # fully trusts the (fake) model


def test_no_model_falls_back_to_rules(tmp_path):
    model, info = ranker.load_model(tmp_path / "missing.joblib")
    assert model is None and info is None


@pytest.mark.parametrize(
    ("value", "target", "expected"),
    [(450, 450, 1.0), (750, 450, 0.0), (600, 450, 0.5), (450, None, 0.5)],
)
def test_closeness(value, target, expected):
    assert features.closeness(value, target, 300) == pytest.approx(expected)
