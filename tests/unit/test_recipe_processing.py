from pathlib import Path

import pytest

from app.datasets import recipenlg, reference
from app.nutrition.food_matcher import IngredientMatcher
from app.processing import features, recipes

FIXTURE = Path(__file__).parents[1] / "fixtures" / "recipenlg_tiny.csv"


@pytest.fixture(scope="module")
def matcher():
    return IngredientMatcher()


@pytest.fixture(scope="module")
def curated(matcher):
    return recipes.records_from_curated(reference.load_curated_recipes(), matcher)


def test_curated_recipes_are_library_ready(curated):
    assert len(curated) == 30
    assert all(r["library_ready"] for r in curated)
    paneer = next(r for r in curated if r["title"] == "Paneer Bhurji")
    assert paneer["origin"] == "curated"
    assert paneer["cuisine_group"] == "indian"
    assert paneer["course"] == "main"
    assert paneer["servings"] == 2
    assert "paneer" in paneer["ingredient_ids"]


def test_recipenlg_row_is_parsed(matcher):
    df = recipenlg.load_sample(FIXTURE)
    records = recipes.records_from_recipenlg(df.head(1), matcher)
    record = records[0]
    assert record["recipe_id"].startswith("rnlg_")
    assert record["ingredient_ids"] == ["egg", "flour"]
    assert record["mapped_ratio"] == 1.0
    assert record["n_steps"] == 2


def test_recipe_ids_are_stable(matcher):
    df = recipenlg.load_sample(FIXTURE).head(2)
    first = [r["recipe_id"] for r in recipes.records_from_recipenlg(df, matcher)]
    second = [r["recipe_id"] for r in recipes.records_from_recipenlg(df, matcher)]
    assert first == second


def _record(matcher, title, lines, steps=("Cook.",), origin="recipenlg"):
    return recipes.build_record(title, list(lines), list(steps), origin=origin, link=title,
                                matcher=matcher)


def test_invalid_recipes_are_removed(matcher):
    too_few = _record(matcher, "Toast", ["1 slice bread", "1 tsp butter"])
    no_steps = _record(matcher, "Mystery", ["1 egg", "1 c. milk", "1 c. flour"], steps=())
    good = _record(matcher, "Pancakes", ["1 egg", "1 c. milk", "1 c. flour"])
    kept, stats = recipes.clean([too_few, no_steps, good])
    assert [r["title"] for r in kept] == ["Pancakes"]
    assert stats["invalid"] == 2


def test_duplicates_removed_and_curated_preferred(matcher):
    lines = ["200 g paneer", "80 g onion", "100 g tomato"]
    web = _record(matcher, "Paneer bhurji", lines)
    ours = _record(matcher, "Paneer Bhurji", lines, origin="curated")
    kept, stats = recipes.clean([web, ours])
    assert len(kept) == 1 and kept[0]["origin"] == "curated"
    assert stats["duplicates"] == 1


def test_recipenlg_cap_keeps_all_curated(matcher, curated):
    web = [_record(matcher, f"Cake {name}", ["1 egg", "1 c. milk", "1 c. flour"])
           for name in ["alpha", "beta", "gamma", "delta", "omega"]]
    kept, _ = recipes.clean(curated + web, max_recipenlg=2)
    assert sum(r["origin"] == "curated" for r in kept) == 30
    assert sum(r["origin"] == "recipenlg" for r in kept) == 2


def test_library_ready_needs_mapping_and_quantities(matcher):
    unmapped = _record(matcher, "Odd", ["1 c. dragonfruit", "1 c. unobtainium", "1 egg"])
    no_qty = _record(matcher, "Vague", ["salt", "1 egg", "1 c. milk"])
    assert unmapped["library_ready"] is False
    assert no_qty["library_ready"] is False


def test_unmapped_names_report(matcher):
    record = _record(matcher, "Odd", ["1 c. dragonfruit", "2 c. dragonfruit", "1 egg"])
    assert recipes.unmapped_names([record]) == [("dragonfruit", 2)]


def test_save_and_load_round_trip(tmp_path, curated):
    path = recipes.save(curated[:3], tmp_path / "r.jsonl")
    df = recipes.load(path)
    assert len(df) == 3
    assert isinstance(df.loc[0, "ingredients"], list)


@pytest.mark.parametrize(
    ("steps", "minutes"),
    [
        (["Bake 30 minutes.", "Cool 10 min."], 40),
        (["Chill 2 hours."], 120),
        (["Simmer 20 to 30 minutes."], 25),
        (["Mix well."], None),
    ],
)
def test_estimate_minutes(steps, minutes):
    assert features.estimate_minutes(steps) == minutes


@pytest.mark.parametrize(
    ("title", "meal_type"),
    [("Chocolate Chip Cookies", "dessert"), ("Fluffy Pancakes", "breakfast"),
     ("Spinach Dip", "snack"), ("Beef Stew", "main"), ("Mango Lassi", "beverage")],
)
def test_guess_meal_type(title, meal_type):
    assert features.guess_meal_type(title) == meal_type


def test_guess_cuisine():
    assert features.guess_cuisine("Chicken Tikka Masala", []) == "indian"
    assert features.guess_cuisine("Veg Stew", ["ghee", "garam_masala"]) == "indian"
    assert features.guess_cuisine("Spaghetti Bake", []) == "italian"
    assert features.guess_cuisine("Pot Roast", []) == "other"


def test_difficulty():
    assert features.difficulty(5, 3) == "easy"
    assert features.difficulty(10, 6) == "medium"
    assert features.difficulty(15, 4) == "hard"
