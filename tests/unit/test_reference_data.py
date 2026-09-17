"""Sanity checks on the hand-curated reference data."""

import re

import pytest

from app.datasets import reference

FDA_MAJOR = {"milk", "egg", "fish", "crustacean", "tree_nut", "peanut", "wheat_gluten", "soy", "sesame"}


def test_allergens_cover_fda_and_fssai_lists():
    df = reference.load_allergens()
    assert set(df.loc[df["fda_major"] == 1, "code"]) == FDA_MAJOR
    fssai = set(df.loc[df["fssai_declared"] == 1, "code"])
    assert {"wheat_gluten", "milk", "soy", "sulphite", "peanut", "tree_nut"} <= fssai


def test_every_allergen_has_keywords_and_keywords_are_clean():
    codes = set(reference.load_allergens()["code"])
    kw = reference.load_allergen_keywords()
    assert set(kw["allergen_code"]) == codes
    assert (kw["keyword"] == kw["keyword"].str.strip().str.lower()).all()
    assert not kw.duplicated().any()


@pytest.mark.parametrize(
    ("code", "word"),
    [("soy", "tofu"), ("soy", "soya chunks"), ("milk", "whey"), ("milk", "paneer"),
     ("milk", "ghee"), ("wheat_gluten", "atta"), ("peanut", "groundnut"), ("sesame", "til")],
)
def test_important_hidden_names_present(code, word):
    kw = reference.load_allergen_keywords()
    assert word in set(kw.loc[kw["allergen_code"] == code, "keyword"])


def test_diets_reference_known_groups():
    groups = set(reference.load_food_group_keywords()["group"])
    diets = reference.load_diets().set_index("diet")
    for excluded in diets["excluded_groups"]:
        assert set(excluded) <= groups
    assert "egg" in diets.loc["vegetarian", "excluded_groups"]  # Indian vegetarian
    assert "egg" not in diets.loc["eggetarian", "excluded_groups"]
    assert "dairy" in diets.loc["vegan", "excluded_groups"]
    assert diets.loc["non_vegetarian", "excluded_groups"] == []


def test_exceptions_point_to_known_codes():
    exc = reference.load_keyword_exceptions()
    allergens = set(reference.load_allergens()["code"])
    groups = set(reference.load_food_group_keywords()["group"])
    assert set(exc["scope"]) <= {"allergen", "group"}
    for _, row in exc.iterrows():
        assert row["code"] in (allergens if row["scope"] == "allergen" else groups)


def test_prices_are_valid():
    prices = reference.load_prices()
    assert prices["item"].is_unique
    assert (prices["price_inr"] > 0).all()
    assert (prices["grams_per_unit"] > 0).all()
    assert set(prices["per_unit"]) <= reference.VALID_PRICE_UNITS
    assert prices["source"].str.len().gt(0).all()


QUANTITY = re.compile(r"^\d+(\.\d+)? (g|ml) \S")


def test_curated_recipes_are_well_formed():
    recipes = reference.load_curated_recipes()
    assert len(recipes) >= 25
    assert recipes["title"].is_unique
    diets = set(reference.load_diets()["diet"])
    for _, r in recipes.iterrows():
        assert r["ingredients"] and r["directions"], r["title"]
        assert len(r["ingredients"]) == len(r["NER"]), r["title"]
        assert all(QUANTITY.match(i) for i in r["ingredients"]), r["title"]
        assert r["diet"] in diets
        assert int(r["servings"]) >= 1 and int(r["cook_minutes"]) > 0


def test_knowledge_base_documents_have_topic_and_sources():
    files = reference.knowledge_base_files()
    assert len(files) >= 6
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\ntopic: "), path.name
        assert "## Sources" in text, path.name
