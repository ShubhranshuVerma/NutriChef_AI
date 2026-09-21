"""Checks against the real USDA-linked table. Skipped if the data hasn't been built."""

import pytest

from app.nutrition.calculator import INGREDIENT_FOODS_PATH, calculate_from_text, load_tables

pytestmark = pytest.mark.skipif(
    not INGREDIENT_FOODS_PATH.exists(), reason="run scripts.build_ingredient_foods first"
)


@pytest.fixture(scope="module")
def tables():
    return load_tables()


def test_one_large_egg(tables):
    r = calculate_from_text(["1 egg"], tables, servings=1)
    assert 60 <= r["per_serving"]["kcal"] <= 90  # USDA: ~72 kcal for a 50 g egg
    assert 5 <= r["per_serving"]["protein_g"] <= 7.5


def test_paneer_bhurji_is_plausible(tables):
    lines = ["200 g paneer", "80 g onion", "100 g tomato", "10 g oil", "2 g salt"]
    r = calculate_from_text(lines, tables, servings=2)
    assert 300 <= r["per_serving"]["kcal"] <= 500
    assert r["per_serving"]["protein_g"] >= 18
    assert r["confidence"] == "high"


def test_calories_roughly_match_macros(tables):
    """Atwater check: kcal ~ 4*protein + 4*carbs + 9*fat (within 20%)."""
    r = calculate_from_text(["1 c. flour", "1/2 c. sugar", "2 eggs", "1/2 c. butter"],
                            tables, servings=1)
    s = r["per_serving"]
    estimate = 4 * s["protein_g"] + 4 * s["carbs_g"] + 9 * s["fat_g"]
    assert abs(estimate - s["kcal"]) / s["kcal"] < 0.2
