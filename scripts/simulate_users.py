"""Create SIMULATED users and their likes/dislikes, so we have data to train on.

This is clearly marked as synthetic: no real people are involved. Once the app
collects real feedback, the same files can be filled from the database instead.

Run from the project root (after scripts.tag_recipes):
    python -m scripts.simulate_users --users 200

Output: data/interactions/users.csv and data/interactions/interactions.csv
"""

import argparse
import random

import pandas as pd

from app.core.config import PROJECT_ROOT
from scripts.tag_recipes import OUTPUT_PATH as TAGGED_PATH

USERS_PATH = PROJECT_ROOT / "data" / "interactions" / "users.csv"
INTERACTIONS_PATH = PROJECT_ROOT / "data" / "interactions" / "interactions.csv"

DIETS = ["vegetarian", "eggetarian", "vegan", "non_vegetarian", "jain"]
CUISINES = ["indian", "italian", "mexican", "asian", "other"]
RECIPES_SEEN_PER_USER = 40


POPULAR_INGREDIENTS = ["paneer", "egg", "chicken", "rice", "atta", "oats", "tomato", "onion",
                       "chickpeas", "milk", "flour", "sugar", "butter", "spinach", "mushroom"]


def make_user(user_id, rng):
    return {
        "user_id": user_id,
        "diet": rng.choice(DIETS),
        "cuisine": rng.choice(CUISINES),
        "kcal_target": rng.choice([350, 450, 550, 650]),
        "protein_target_g": rng.choice([10, 15, 20, 25]),
        "budget_per_meal_inr": rng.choice([20, 40, 60, 100]),
        "max_cook_minutes": rng.choice([20, 30, 45, 60]),
        # favourite ingredients and a taste for simple recipes: the parts a fixed
        # rule cannot know, and that the model has to learn
        "liked_ingredients": ";".join(rng.sample(POPULAR_INGREDIENTS, 3)),
        "likes_simple_recipes": rng.random() < 0.5,
        "synthetic": True,
    }


def like_probability(user, recipe, rng):
    """The hidden 'taste' we are asking the model to learn, plus noise."""
    score = 0.0
    if user["diet"] in recipe["suitable_diets"]:
        score += 0.35
    if recipe["cuisine_group"] == user["cuisine"]:
        score += 0.20
    if abs((recipe["kcal"] or 0) - user["kcal_target"]) < 150:
        score += 0.15
    if (recipe["protein_g"] or 0) >= user["protein_target_g"]:
        score += 0.15
    if (recipe["cost_per_serving_inr"] or 0) <= user["budget_per_meal_inr"]:
        score += 0.10
    if (recipe["cook_minutes"] or 0) <= user["max_cook_minutes"]:
        score += 0.05
    favourites = set(user["liked_ingredients"].split(";"))
    if favourites & set(recipe["ingredient_ids"] or []):
        score += 0.30
    if user["likes_simple_recipes"] and (recipe["n_ingredients"] or 0) <= 8:
        score += 0.15
    if recipe["origin"] == "curated":
        score += 0.10
    return min(0.95, max(0.05, score + rng.uniform(-0.15, 0.15)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not TAGGED_PATH.exists():
        print("Run scripts.tag_recipes first.")
        return

    rng = random.Random(args.seed)
    recipes = pd.read_json(TAGGED_PATH, lines=True)
    recipes = recipes[recipes["library_ready"]].to_dict("records")
    print(f"Using {len(recipes):,} library-ready recipes")

    users, interactions = [], []
    for i in range(args.users):
        user = make_user(f"sim_{i:04d}", rng)
        users.append(user)
        for step, recipe in enumerate(rng.sample(recipes, min(RECIPES_SEEN_PER_USER, len(recipes)))):
            liked = rng.random() < like_probability(user, recipe, rng)
            interactions.append({
                "user_id": user["user_id"],
                "recipe_id": recipe["recipe_id"],
                "step": step,  # order in which the user saw recipes (used for the test split)
                "event": "like" if liked else "skip",
                "liked": int(liked),
                "synthetic": True,
            })

    USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(users).to_csv(USERS_PATH, index=False)
    pd.DataFrame(interactions).to_csv(INTERACTIONS_PATH, index=False)
    print(f"Saved {len(users)} users -> {USERS_PATH}")
    print(f"Saved {len(interactions):,} interactions -> {INTERACTIONS_PATH}")
    print(f"Liked: {sum(i['liked'] for i in interactions) / len(interactions):.1%}")


if __name__ == "__main__":
    main()
