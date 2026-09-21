"""Features for the recipe ranking model.

One row per (user, recipe) pair. All features are numbers between 0 and 1
(except protein_g, which is scaled), so they are easy to read and compare.
"""

FEATURE_NAMES = [
    "calorie_fit", "protein_fit", "cost_fit", "time_fit",
    "cuisine_match", "diet_match", "ingredient_overlap", "inventory_use",
    "is_indian", "is_curated", "n_ingredients_scaled",
]


def closeness(value, target, tolerance):
    """1.0 when value == target, falling to 0.0 when it is `tolerance` away."""
    if not target or value is None:
        return 0.5  # no preference given
    difference = abs(value - target)
    return max(0.0, 1.0 - difference / tolerance)


def at_most(value, limit):
    """1.0 when the value is within the limit, dropping as it goes over."""
    if not limit or value is None:
        return 0.5
    if value <= limit:
        return 1.0
    return max(0.0, 1.0 - (value - limit) / limit)


def at_least(value, target):
    """1.0 when the value reaches the target (e.g. enough protein)."""
    return at_most(target, value)


def overlap(items, liked_items):
    if not items or not liked_items:
        return 0.0
    return len(set(items) & set(liked_items)) / len(set(items))


def build_features(user, recipe):
    """user: profile dict, recipe: tagged recipe dict -> dict of features."""
    return {
        "calorie_fit": closeness(recipe.get("kcal"), user.get("kcal_target"), 300),
        "protein_fit": at_least(recipe.get("protein_g") or 0, user.get("protein_target_g")),
        "cost_fit": at_most(recipe.get("cost_per_serving_inr"), user.get("budget_per_meal_inr")),
        "time_fit": at_most(recipe.get("cook_minutes"), user.get("max_cook_minutes")),
        "cuisine_match": float(recipe.get("cuisine_group") == user.get("cuisine")),
        "diet_match": float(user.get("diet") in (recipe.get("suitable_diets") or [])),
        "ingredient_overlap": overlap(recipe.get("ingredient_ids"), user.get("liked_ingredients")),
        "inventory_use": overlap(recipe.get("ingredient_ids"), user.get("inventory")),
        "is_indian": float(recipe.get("cuisine_group") == "indian"),
        "is_curated": float(recipe.get("origin") == "curated"),
        "n_ingredients_scaled": min(recipe.get("n_ingredients", 0), 20) / 20,
    }


def feature_row(user, recipe):
    """Features as a plain list, in the order of FEATURE_NAMES."""
    values = build_features(user, recipe)
    return [values[name] for name in FEATURE_NAMES]
