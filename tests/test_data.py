"""Turning raw recipes into the library: the curated Indian recipes, and meal-type guesses."""

import pytest

from app.data import features, recipes, reference
from app.nutrition.food_matcher import IngredientMatcher


@pytest.fixture(scope="module")
def curated():
    return recipes.records_from_curated(reference.load_curated_recipes(), IngredientMatcher())


def test_every_curated_recipe_makes_it_into_the_library(curated):
    assert len(curated) == len(reference.load_curated_recipes())
    assert all(r["library_ready"] for r in curated)


def test_a_curated_recipe_is_read_correctly(curated):
    paneer = next(r for r in curated if r["title"] == "Paneer Bhurji")
    assert paneer["cuisine_group"] == "indian"
    assert paneer["course"] == "main"
    assert paneer["servings"] == 2
    assert "paneer" in paneer["ingredient_ids"]


@pytest.mark.parametrize(
    ("title", "meal_type"),
    [("Fluffy Pancakes", "breakfast"),
     # These two used to fall through to "main" and were served as dinner.
     ("Easy Vegan Hot Chocolate", "beverage"), ("Corn And Black Bean Salsa", "side")],
)
def test_meal_type_is_guessed_from_the_title(title, meal_type):
    assert features.guess_meal_type(title) == meal_type
