"""Workflow tests: fake LLM, fake nutrition tables, real rules."""

import json

import pytest

from app.agents import graph
from app.core.llm import FakeLLM
from app.services.recipe_service import build_result
from app.validation.checks import load_rules

REQUIREMENTS = json.dumps({
    "diet": "eggetarian", "allergies": ["soy"], "exclude": ["whey"],
    "have_ingredients": ["paneer", "eggs"], "course": "main", "max_kcal": 600,
    "min_protein_g": 25,
})
GOOD_RECIPE = json.dumps({
    "title": "Paneer Egg Bhurji", "servings": 2,
    "ingredients": ["200 g paneer", "100 g egg", "80 g onion", "10 g oil"],
    "steps": ["Fry the onion.", "Add paneer and egg."], "notes": "",
})
TOFU_RECIPE = json.dumps({
    "title": "Tofu Bhurji", "servings": 2,
    "ingredients": ["200 g tofu", "80 g onion", "10 g oil"],
    "steps": ["Cook the tofu."], "notes": "",
})
NO_PROBLEMS = json.dumps({"problems": [], "suggestions": []})
HAS_PROBLEMS = json.dumps({"problems": ["uses soy"], "suggestions": ["use paneer instead"]})


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture
def tables():
    catalog = {name: {"category": category, "density_g_ml": 1.0, "grams_per_piece": 50,
                      "nutrition_source": "usda"}
               for name, category in [("paneer", "dairy"), ("egg", "egg"), ("onion", "vegetable"),
                                      ("oil", "oil_fat"), ("tofu", "soy")]}
    nutrients = {
        "paneer": {"kcal": 300, "protein_g": 22, "carbs_g": 2, "fat_g": 22, "fiber_g": 0},
        "egg": {"kcal": 143, "protein_g": 12.6, "carbs_g": 0.7, "fat_g": 9.5, "fiber_g": 0},
        "onion": {"kcal": 40, "protein_g": 1.1, "carbs_g": 9.3, "fat_g": 0.1, "fiber_g": 1.7},
        "oil": {"kcal": 884, "protein_g": 0, "carbs_g": 0, "fat_g": 100, "fiber_g": 0},
        "tofu": {"kcal": 144, "protein_g": 17, "carbs_g": 3, "fat_g": 9, "fiber_g": 2},
    }

    from app.nutrition.food_matcher import IngredientMatcher

    return {"catalog": catalog, "nutrients": nutrients,
            "price_per_gram": {"paneer": 0.4, "egg": 0.14}, "matcher": IngredientMatcher()}


def deps_for(replies, tables, rules, search=None):
    return {"llm": FakeLLM(replies), "tables": tables, "rules": rules, "search_recipes": search}


def test_happy_path_finishes_without_revisions(tables, rules):
    deps = deps_for([REQUIREMENTS, GOOD_RECIPE, NO_PROBLEMS], tables, rules)
    state = graph.run("vegetarian, allergic to soy...", deps)
    assert state["status"] == "ok"
    assert state["revisions"] == 0
    assert state["checks"]["passed"] is True
    assert [s["step"] for s in state["trace"]] == [
        "understand", "search", "write", "check", "critique", "finish"]


def test_unsafe_recipe_is_revised_then_accepted(tables, rules):
    """First draft uses tofu (soy allergy). The loop must fix it."""
    deps = deps_for([REQUIREMENTS, TOFU_RECIPE, HAS_PROBLEMS, GOOD_RECIPE, NO_PROBLEMS],
                    tables, rules)
    state = graph.run("vegetarian, allergic to soy...", deps)
    assert state["revisions"] == 1
    assert state["status"] == "ok"
    assert "soy" not in state["recipe"]["allergens"]


def test_gives_up_after_two_revisions_and_reports_failure(tables, rules):
    """The LLM keeps returning tofu, so the workflow must end as 'failed'."""
    deps = deps_for([REQUIREMENTS] + [TOFU_RECIPE, HAS_PROBLEMS] * 3, tables, rules)
    state = graph.run("vegetarian, allergic to soy...", deps)
    assert state["revisions"] == graph.MAX_REVISIONS
    assert state["status"] == "failed"
    assert any("soy" in failure for failure in state["checks"]["failures"])


def test_nutrition_is_calculated_not_taken_from_the_llm(tables, rules):
    deps = deps_for([REQUIREMENTS, GOOD_RECIPE, NO_PROBLEMS], tables, rules)
    state = graph.run("anything", deps)
    per_serving = state["nutrition"]["per_serving"]
    # paneer 600 + egg 143 + onion 32 + oil 88 = 863 kcal over 2 servings
    assert per_serving["kcal"] == 432
    # protein: paneer 44 + egg 12.6 + onion 0.9 = 57.5 over 2 servings
    assert per_serving["protein_g"] == pytest.approx(28.7, abs=0.2)


def test_search_results_reach_the_recipe_prompt(tables, rules):
    hits = [{"text": "Palak Paneer: 250 g spinach, 150 g paneer",
             "metadata": {"source_url": "http://example.com/palak"}}]
    deps = deps_for([REQUIREMENTS, GOOD_RECIPE, NO_PROBLEMS], tables, rules,
                    search=lambda query, **filters: hits)
    state = graph.run("anything", deps)
    assert "Palak Paneer" in deps["llm"].prompts[1]
    assert state["sources"] == ["http://example.com/palak"]


def test_profile_allergies_are_added(tables, rules):
    # the recipe keeps using paneer, so the loop tries twice and then gives up
    deps = deps_for([REQUIREMENTS] + [GOOD_RECIPE, NO_PROBLEMS] * 3, tables, rules)
    state = graph.run("anything", deps, profile={"allergies": ["milk"]})
    assert state["constraints"].allergies == ["milk", "soy"]
    # paneer is milk, so the recipe must fail the checks
    assert state["status"] == "failed"


def test_build_result_shape(tables, rules):
    deps = deps_for([REQUIREMENTS, GOOD_RECIPE, NO_PROBLEMS], tables, rules)
    result = build_result(graph.run("anything", deps))
    assert result["status"] == "ok"
    assert result["recipe"]["ingredients"][0] == "200 g paneer"
    assert result["nutrition_per_serving"]["kcal"] > 0
    assert "estimates" in result["disclaimer"]
