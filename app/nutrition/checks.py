"""Allergen, diet and constraint checks - plain Python, no LLM.

Two steps:
1. `tag_recipe`  - what a recipe contains (allergens, food groups, diets it suits).
2. `check_recipe` - whether it fits one person's request (hard rules and warnings).

Keyword matching is whole-word only, so "eggplant" never counts as "egg".
An exceptions list keeps "coconut milk" from counting as milk.
"""

import re

from app.data.reference import (
    load_allergen_keywords,
    load_diets,
    load_food_group_keywords,
    load_keyword_exceptions,
)
from app.nutrition.food_matcher import load_catalog

MIN_CONFIDENCE_FOR_PASS = "high"


def load_rules():
    """Load the reference tables into simple dictionaries."""
    allergens = {}
    for row in load_allergen_keywords().itertuples():
        allergens.setdefault(row.allergen_code, []).append(row.keyword)

    groups = {}
    for row in load_food_group_keywords().itertuples():
        groups.setdefault(row.group, []).append(row.keyword)

    exceptions = {}
    for row in load_keyword_exceptions().itertuples():
        exceptions.setdefault((row.scope, row.code), []).append(row.phrase)

    diets = {row.diet: row.excluded_groups for row in load_diets().itertuples()}
    catalog = load_catalog().set_index("ingredient_id")["name"].to_dict()
    return {"allergens": allergens, "groups": groups, "exceptions": exceptions,
            "diets": diets, "catalog_names": catalog}


def contains_word(text, phrase):
    """True if `phrase` appears in `text` as whole words (a plural 's' is allowed).

    "2 eggs" contains "egg", but "1 eggplant" does not.
    """
    pattern = rf"(?<![a-z]){re.escape(phrase)}(?:es|s)?(?![a-z])"
    return re.search(pattern, text.lower()) is not None


def _clean(text, phrases):
    """Remove known exception phrases, e.g. 'coconut milk' before looking for 'milk'."""
    for phrase in phrases:
        text = text.lower().replace(phrase, " ")
    return text


def ingredient_texts(ingredients, rules):
    """One text per ingredient: its name plus its catalog name, if known."""
    texts = []
    for item in ingredients:
        name = str(item.get("name", ""))
        catalog_name = rules["catalog_names"].get(item.get("ingredient_id"), "")
        texts.append(f"{name} {catalog_name}".strip().lower())
    return texts


def find_matches(texts, keyword_map, rules, scope):
    """Which codes (allergens or food groups) appear in these ingredient texts."""
    found = []
    for code, keywords in keyword_map.items():
        exceptions = rules["exceptions"].get((scope, code), [])
        for text in texts:
            cleaned = _clean(text, exceptions)
            if any(contains_word(cleaned, keyword) for keyword in keywords):
                found.append(code)
                break
    return sorted(found)


def diets_allowed(food_groups, rules):
    """Which diets a recipe with these food groups is suitable for."""
    return sorted(
        diet for diet, excluded in rules["diets"].items()
        if not set(excluded) & set(food_groups)
    )


def tag_recipe(recipe, rules):
    """Add `allergens`, `food_groups` and `suitable_diets` to a recipe dict."""
    texts = ingredient_texts(recipe.get("ingredients", []), rules)
    allergens = find_matches(texts, rules["allergens"], rules, "allergen")
    groups = find_matches(texts, rules["groups"], rules, "group")
    return {**recipe, "allergens": allergens, "food_groups": groups,
            "suitable_diets": diets_allowed(groups, rules)}


def nutrition_looks_wrong(recipe):
    """Protein, carbs and fat cannot supply more calories than the recipe has."""
    kcal = recipe.get("kcal") or 0
    from_macros = 4 * (recipe.get("protein_g") or 0) + 4 * (recipe.get("carbs_g") or 0) \
        + 9 * (recipe.get("fat_g") or 0)
    return kcal > 0 and from_macros > kcal * 1.25


def check_recipe(recipe, request, rules):
    """Check a tagged recipe against one request.

    request keys (all optional):
      allergies, exclude, diet, max_kcal, min_protein_g, max_cook_minutes, max_cost_inr, cuisine
    Hard rules must pass; warnings are only reported.
    """
    failures, warnings = [], []
    texts = ingredient_texts(recipe.get("ingredients", []), rules)

    # --- hard: allergens ---
    for allergen in request.get("allergies", []):
        if allergen in recipe.get("allergens", []):
            failures.append(f"contains {allergen}")

    # --- hard: excluded ingredients (free text, e.g. "whey") ---
    for word in request.get("exclude", []):
        if any(contains_word(text, word.lower()) for text in texts):
            failures.append(f"contains excluded ingredient: {word}")

    # --- hard: diet ---
    diet = request.get("diet")
    if diet:
        blocked = set(rules["diets"].get(diet, [])) & set(recipe.get("food_groups", []))
        if blocked:
            failures.append(f"not {diet}: contains {', '.join(sorted(blocked))}")

    # --- hard: calories and cost per serving ---
    if request.get("max_kcal") and (recipe.get("kcal") or 0) > request["max_kcal"]:
        failures.append(f"{recipe['kcal']} kcal is above the limit of {request['max_kcal']}")
    if request.get("max_cost_inr") and (recipe.get("cost_per_serving_inr") or 0) > request["max_cost_inr"]:
        failures.append(f"costs about Rs {recipe['cost_per_serving_inr']} per serving")

    # --- hard: we must trust the numbers ---
    if recipe.get("nutrition_confidence") and recipe["nutrition_confidence"] != MIN_CONFIDENCE_FOR_PASS:
        failures.append(f"nutrition confidence is {recipe['nutrition_confidence']}")
    if nutrition_looks_wrong(recipe):
        failures.append("nutrition numbers look wrong (macros exceed calories)")

    # --- warnings (soft) ---
    if request.get("min_protein_g") and (recipe.get("protein_g") or 0) < request["min_protein_g"]:
        warnings.append(f"only {recipe.get('protein_g', 0)} g protein per serving")
    if request.get("max_cook_minutes") and (recipe.get("cook_minutes") or 0) > request["max_cook_minutes"]:
        warnings.append(f"takes about {recipe['cook_minutes']} minutes")
    if request.get("cuisine") and recipe.get("cuisine_group") != request["cuisine"]:
        warnings.append(f"cuisine is {recipe.get('cuisine_group')}, not {request['cuisine']}")

    return {"passed": not failures, "failures": failures, "warnings": warnings}
