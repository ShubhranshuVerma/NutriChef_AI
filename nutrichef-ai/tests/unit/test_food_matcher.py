import pandas as pd
import pytest

from app.nutrition.food_matcher import (
    IngredientMatcher,
    load_catalog,
    normalize_name,
    pick_ner_name,
    resolve_usda,
)


@pytest.fixture(scope="module")
def matcher():
    return IngredientMatcher()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("firmly packed brown sugar", "brown_sugar"),
        ("sugar", "sugar"),
        ("eggs", "egg"),
        ("eggplant", "brinjal"),  # must not match "egg"
        ("large egg whites", "egg_white"),
        ("coconut milk", "coconut_milk"),  # must not match "milk"
        ("peanut butter", "peanut_butter"),
        ("cream cheese", "cream_cheese"),
        ("green bell pepper", "capsicum"),
        ("freshly ground black pepper", "black_pepper"),
        ("red kidney beans", "rajma"),
        ("chana dal", "chana_dal"),
        ("kabuli chana", "chickpeas"),
        ("garlic cloves", "garlic"),
        ("whole wheat flour", "atta"),
        ("maida", "flour"),
        ("dahi", "curd"),
        ("hari mirch", "green_chilli"),
        ("cooked rice", "cooked_rice"),
        ("tomatoes", "tomato"),
        ("soya chunks", "soya_chunks"),
    ],
)
def test_match(matcher, name, expected):
    assert matcher.match(name) == expected


@pytest.mark.parametrize("name", ["", "unicorn dust", "xyz"])
def test_unknown_names_return_none(matcher, name):
    assert matcher.match(name) is None


def test_normalize_name_removes_descriptors():
    assert normalize_name("2 Large, finely CHOPPED onions (red)") == "onions"


def test_pick_ner_name_prefers_longest_entity():
    ner = ["sugar", "brown sugar", "milk"]
    assert pick_ner_name("1 c. firmly packed brown sugar", ner) == "brown sugar"
    assert pick_ner_name("1 c. water", ner) is None


def test_catalog_is_consistent():
    catalog = load_catalog()
    assert catalog["ingredient_id"].is_unique
    assert set(catalog["nutrition_source"]) <= {"usda", "usda_proxy", "negligible"}
    needs_usda = catalog["nutrition_source"] != "negligible"
    assert (catalog.loc[needs_usda, "usda_description"] != "").all()
    assert (catalog["density_g_ml"] > 0).all()
    proxies = catalog[catalog["nutrition_source"] == "usda_proxy"]
    assert proxies["notes"].str.startswith("PROXY").all()


def test_curated_recipe_ingredients_are_all_in_catalog(matcher):
    from app.datasets.reference import load_curated_recipes

    for recipe in load_curated_recipes().itertuples():
        for name in recipe.NER:
            assert matcher.match(name), f"{recipe.title}: {name}"


def test_aliases_are_not_shared_between_ingredients():
    catalog = load_catalog()
    seen = {}
    for row in catalog.itertuples():
        for alias in [row.name, *filter(None, row.aliases.split(";"))]:
            key = alias.strip().lower()
            assert seen.setdefault(key, row.ingredient_id) == row.ingredient_id, key


@pytest.fixture
def usda_foods():
    descriptions = [
        "Egg, whole, raw, fresh",
        "Onions, raw, sweet",
        "Oats (Includes foods for USDA's Food Distribution Program)",
        "Sweet Potato puffs, frozen, unprepared",
        "Sweet potato, raw, unprepared (Includes foods for USDA's Food Distribution Program)",
        "Yogurt, Greek, plain, lowfat",
    ]
    n = len(descriptions)
    return pd.DataFrame({
        "fdc_id": range(1, n + 1), "description": descriptions, "category": ["x"] * n,
        "kcal": [143, 32, 389, 200, 86, 73], "protein_g": [12.6] * n, "carbs_g": [1.0] * n,
        "fat_g": [1.0] * n, "fiber_g": [0.0] * n,
    })


def _catalog(rows):
    return pd.DataFrame(rows, columns=["ingredient_id", "usda_description", "nutrition_source",
                                       "usda_fdc_id"])


def test_resolve_usda_match_types(usda_foods):
    catalog = _catalog([
        ("egg", "Egg, whole, raw, fresh", "usda", ""),
        ("onion", "Onions, raw", "usda", ""),
        ("oats", "Oats", "usda", ""),
        ("sweet_potato", "Sweet potato, raw, unprepared", "usda", ""),
        ("greek_yogurt", "Yogurt, Greek, plain, nonfat", "usda", ""),
        ("unicorn", "Unicorn, raw", "usda", ""),
        ("water", "", "negligible", ""),
        ("pinned", "anything", "usda", "1"),
    ])
    out = resolve_usda(catalog, usda_foods).set_index("ingredient_id")
    assert out.loc["egg", "match_type"] == "exact" and out.loc["egg", "kcal"] == 143
    assert out.loc["onion", "match_type"] == "prefix" and out.loc["onion", "fdc_id"] == 2
    assert out.loc["oats", "match_type"] == "exact" and out.loc["oats", "fdc_id"] == 3
    # must pick the real sweet potato, not "Sweet Potato puffs"
    assert out.loc["sweet_potato", "fdc_id"] == 5
    assert out.loc["greek_yogurt", "match_type"] == "fuzzy"
    assert out.loc["unicorn", "match_type"] == "missing"
    assert out.loc["water", "match_type"] == "negligible" and out.loc["water", "kcal"] == 0
    assert out.loc["pinned", "match_type"] == "manual" and out.loc["pinned", "fdc_id"] == 1


def test_manual_id_that_does_not_exist_is_missing(usda_foods):
    out = resolve_usda(_catalog([("x", "Egg, whole, raw, fresh", "usda", "999")]), usda_foods)
    assert out.loc[0, "match_type"] == "missing"
