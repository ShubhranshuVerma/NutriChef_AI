"""Small hand-made data shared by the tests. No data files, no LLM."""

import json

from app.nutrition.food_matcher import IngredientMatcher


def make_recipe(recipe_id, title, course="main", kcal=500, protein_g=30, cost=40,
                ingredient_ids=None, allergens=None, diets=None, cost_coverage=1.0):
    """A tagged library recipe with just the fields the planner uses."""
    ingredient_ids = ingredient_ids or ["paneer", "onion"]
    return {
        "recipe_id": recipe_id, "title": title, "course": course, "origin": "curated",
        "kcal": kcal, "protein_g": protein_g, "carbs_g": 20, "fat_g": 15,
        "cost_per_serving_inr": cost, "cook_minutes": 30, "servings": 2,
        "cuisine_group": "indian", "n_ingredients": len(ingredient_ids),
        "ingredient_ids": ingredient_ids,
        "ingredients": [{"name": i, "ingredient_id": i, "quantity": 100, "unit": "g"}
                        for i in ingredient_ids],
        "allergens": allergens if allergens is not None else [],
        "food_groups": ["dairy"] if not diets else [],
        "suitable_diets": diets if diets is not None else ["vegetarian", "eggetarian"],
        "nutrition_confidence": "high", "library_ready": True,
        "cost_coverage": cost_coverage,
    }


def small_library():
    return [
        make_recipe("r1", "Paneer Bhurji", ingredient_ids=["paneer", "onion"]),
        make_recipe("r2", "Rajma Masala", ingredient_ids=["kidney_bean", "onion"]),
        make_recipe("r3", "Chana Masala", ingredient_ids=["chickpea", "tomato"]),
        make_recipe("r4", "Besan Chilla", course="breakfast", kcal=350,
                    ingredient_ids=["gram_flour", "onion"]),
        make_recipe("r5", "Poha", course="breakfast", kcal=320, ingredient_ids=["rice", "peanut"]),
        make_recipe("r6", "Oats Upma", course="breakfast", kcal=300,
                    ingredient_ids=["oats", "carrot"]),
    ]


# What the planner needs to weigh and price a shopping list.
PLAN_TABLES = {
    "catalog": {name: {"density_g_ml": None, "grams_per_piece": None, "category": "vegetable",
                       "nutrition_source": "usda"}
                for name in ["paneer", "onion", "kidney_bean", "chickpea", "tomato",
                             "gram_flour", "rice", "peanut", "oats", "carrot"]},
    "price_per_gram": {"paneer": 0.4, "onion": 0.05},
}


def recipe_tables():
    """Nutrition tables for the recipe workflow: five foods, per 100 g."""
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
    return {"catalog": catalog, "nutrients": nutrients,
            "price_per_gram": {"paneer": 0.4, "egg": 0.14}, "matcher": IngredientMatcher()}


# Scripted Gemini replies for the recipe workflow.
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
TOFU_RECIPE = json.dumps({            # soy, for someone allergic to soy - and low on protein
    "title": "Tofu Bhurji", "servings": 2,
    "ingredients": ["200 g tofu", "80 g onion", "10 g oil"],
    "steps": ["Cook the tofu."], "notes": "",
})
SOY_BUT_OTHERWISE_FINE = json.dumps({  # soy, but nothing else wrong: no warnings at all
    "title": "Tofu Stir Fry", "servings": 2,
    "ingredients": ["300 g tofu", "80 g onion", "10 g oil"],
    "steps": ["Stir-fry everything."], "notes": "",
})
LOW_PROTEIN = json.dumps({            # passes every hard rule, misses the protein target
    "title": "Light Paneer Salad", "servings": 2,
    "ingredients": ["50 g paneer", "80 g onion", "10 g oil"],
    "steps": ["Toss everything together."], "notes": "",
})
