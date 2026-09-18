import pytest

from app.validation import checks


@pytest.fixture(scope="module")
def rules():
    return checks.load_rules()


def recipe(names, **fields):
    ingredients = [{"name": n, "ingredient_id": None} for n in names]
    return {"ingredients": ingredients, "kcal": 400, "protein_g": 20, "carbs_g": 30,
            "fat_g": 15, "nutrition_confidence": "high", **fields}


def test_contains_word_is_whole_word_only():
    assert checks.contains_word("2 eggs, beaten", "egg")
    assert not checks.contains_word("1 eggplant", "egg")
    assert checks.contains_word("soya chunks", "soya chunks")


def test_finds_allergens_including_hidden_names(rules):
    tagged = checks.tag_recipe(recipe(["paneer", "whey protein", "atta", "tofu"]), rules)
    assert set(tagged["allergens"]) == {"milk", "wheat_gluten", "soy"}


def test_exceptions_prevent_false_allergens(rules):
    tagged = checks.tag_recipe(recipe(["coconut milk", "peanut butter"]), rules)
    assert "milk" not in tagged["allergens"]
    assert tagged["allergens"] == ["peanut"]


def test_food_groups_and_suitable_diets(rules):
    veg = checks.tag_recipe(recipe(["paneer", "spinach"]), rules)
    assert veg["food_groups"] == ["dairy"]
    assert "vegetarian" in veg["suitable_diets"]
    assert "vegan" not in veg["suitable_diets"]

    with_egg = checks.tag_recipe(recipe(["eggs", "onion"]), rules)
    assert "eggetarian" in with_egg["suitable_diets"]
    assert "vegetarian" not in with_egg["suitable_diets"]  # Indian vegetarian excludes eggs
    assert "jain" not in with_egg["suitable_diets"]  # onion

    vegan = checks.tag_recipe(recipe(["tofu", "rice"]), rules)
    assert "vegan" in vegan["suitable_diets"]


def test_allergy_blocks_recipe(rules):
    tagged = checks.tag_recipe(recipe(["tofu", "rice"]), rules)
    result = checks.check_recipe(tagged, {"allergies": ["soy"]}, rules)
    assert result["passed"] is False
    assert result["failures"] == ["contains soy"]


def test_excluded_ingredient_blocks_recipe(rules):
    tagged = checks.tag_recipe(recipe(["whey protein", "banana"]), rules)
    result = checks.check_recipe(tagged, {"exclude": ["whey"]}, rules)
    assert "contains excluded ingredient: whey" in result["failures"]


def test_diet_blocks_recipe(rules):
    tagged = checks.tag_recipe(recipe(["chicken", "rice"]), rules)
    result = checks.check_recipe(tagged, {"diet": "vegetarian"}, rules)
    assert result["passed"] is False
    assert "not vegetarian" in result["failures"][0]


def test_calorie_and_cost_limits(rules):
    tagged = checks.tag_recipe(recipe(["rice"], kcal=700, cost_per_serving_inr=90), rules)
    result = checks.check_recipe(tagged, {"max_kcal": 600, "max_cost_inr": 50}, rules)
    assert len(result["failures"]) == 2


def test_warnings_do_not_fail_the_recipe(rules):
    tagged = checks.tag_recipe(recipe(["rice"], protein_g=8, cook_minutes=60,
                                      cuisine_group="italian"), rules)
    result = checks.check_recipe(
        tagged, {"min_protein_g": 25, "max_cook_minutes": 30, "cuisine": "indian"}, rules
    )
    assert result["passed"] is True
    assert len(result["warnings"]) == 3


def test_low_confidence_fails(rules):
    tagged = checks.tag_recipe(recipe(["rice"], nutrition_confidence="low"), rules)
    assert checks.check_recipe(tagged, {}, rules)["passed"] is False


def test_impossible_nutrition_is_caught(rules):
    bad = recipe(["rice"], kcal=300, protein_g=280, carbs_g=10, fat_g=5)
    assert checks.nutrition_looks_wrong(bad) is True
    assert checks.check_recipe(checks.tag_recipe(bad, rules), {}, rules)["passed"] is False


def test_scenario_one_request(rules):
    """Vegetarian, allergic to soy, no whey, high-protein dinner under 600 kcal."""
    request = {"diet": "eggetarian", "allergies": ["soy"], "exclude": ["whey"],
               "max_kcal": 600, "min_protein_g": 25}
    good = checks.tag_recipe(
        recipe(["paneer", "eggs", "spinach", "oil"], kcal=420, protein_g=30), rules)
    assert checks.check_recipe(good, request, rules)["passed"] is True

    tofu_version = checks.tag_recipe(recipe(["tofu", "spinach"], kcal=300), rules)
    assert checks.check_recipe(tofu_version, request, rules)["passed"] is False
