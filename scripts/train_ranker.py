"""Train the recipe ranking model and log the run to MLflow.

Run from the project root (after scripts.build_data):
    python -m scripts.train_ranker              # 200 simulated users
    python -m scripts.train_ranker --users 500

Two parts:
1. SIMULATE users and their likes and skips, so there is something to learn from.
   It is clearly marked synthetic - no real people are involved. Once the app has
   real feedback, the same two files can be filled from the database instead.
2. TRAIN two models, compare them with the plain rule score on each user's most
   recent interactions, log everything to MLflow, and save the better model.

Saves: data/interactions/*.csv (the practice data) and ml/artifacts/ranker.joblib
"""

import argparse
import json
import os
import random

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import joblib
import mlflow
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.core.config import get_settings
from app.ml.features import FEATURE_NAMES, feature_row
from app.ml.metrics import average_metrics
from app.ml.ranker import (INTERACTIONS_PATH, MODEL_INFO_PATH, MODEL_PATH, RULE_WEIGHTS,
                           USERS_PATH)
from app.services.planner import LIBRARY_PATH as TAGGED_PATH

TEST_SHARE = 0.2  # each user's last 20% of interactions are the test set
K = 5


# ---------- 1. simulated users ----------


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

def simulate(n_users, seed=42):
    """Make the practice users and what each of them liked or skipped."""
    rng = random.Random(seed)
    recipes = pd.read_json(TAGGED_PATH, lines=True)
    recipes = recipes[recipes["library_ready"]].to_dict("records")

    users, interactions = [], []
    for i in range(n_users):
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
    print(f"Simulated {len(users)} users and {len(interactions):,} interactions "
          f"({sum(i['liked'] for i in interactions) / len(interactions):.1%} liked)")


# ---------- 2. training ----------

def build_dataset():
    """One row per interaction, with features and the 'liked' label."""
    users = {}
    for user in pd.read_csv(USERS_PATH).to_dict("records"):
        user["liked_ingredients"] = str(user.get("liked_ingredients", "")).split(";")
        users[user["user_id"]] = user
    recipes = pd.read_json(TAGGED_PATH, lines=True).set_index("recipe_id").to_dict("index")
    interactions = pd.read_csv(INTERACTIONS_PATH)

    rows = []
    for row in interactions.itertuples():
        recipe = recipes.get(row.recipe_id)
        if recipe is None:
            continue
        recipe = {**recipe, "recipe_id": row.recipe_id}
        features = feature_row(users[row.user_id], recipe)
        rows.append([row.user_id, row.recipe_id, row.step, *features, row.liked])
    return pd.DataFrame(rows, columns=["user_id", "recipe_id", "step", *FEATURE_NAMES, "liked"])


def split_by_time(data):
    """Train on what each user saw first, test on what they saw last (no leakage)."""
    train, test = [], []
    for _, group in data.groupby("user_id"):
        group = group.sort_values("step")
        cut = int(len(group) * (1 - TEST_SHARE))
        train.append(group.iloc[:cut])
        test.append(group.iloc[cut:])
    return pd.concat(train), pd.concat(test)


def ranking_scores(test, scores):
    """Group the test rows per user and measure the ranking quality."""
    test = test.assign(score=scores)
    results = []
    for _, group in test.groupby("user_id"):
        ranked = group.sort_values("score", ascending=False)["recipe_id"].tolist()
        liked = set(group.loc[group["liked"] == 1, "recipe_id"])
        results.append((ranked, liked))
    return average_metrics(results, k=K)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--users", type=int, default=200, help="how many users to simulate")
    args = parser.parse_args()

    if not TAGGED_PATH.exists():
        print("The recipe library is missing - run: python -m scripts.build_data")
        return
    simulate(args.users)

    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment_name)

    data = build_dataset()
    train, test = split_by_time(data)
    print(f"{len(data):,} rows: {len(train):,} train / {len(test):,} test "
          f"({data['liked'].mean():.1%} liked)")

    models = {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
        "gradient_boosting": GradientBoostingClassifier(random_state=42),
    }

    # Baseline: the rule score, with no learning at all.
    baseline = [rule_score_from_features(row) for _, row in test.iterrows()]
    results = {"rule_baseline": {"roc_auc": roc_auc_score(test["liked"], baseline),
                                 **ranking_scores(test, baseline)}}

    best_name, best_model, best_score = None, None, -1
    for name, model in models.items():
        with mlflow.start_run(run_name=name):
            model.fit(train[FEATURE_NAMES], train["liked"])
            probabilities = model.predict_proba(test[FEATURE_NAMES])[:, 1]
            metrics = {"roc_auc": roc_auc_score(test["liked"], probabilities),
                       **ranking_scores(test, probabilities)}
            results[name] = metrics

            mlflow.log_param("model", name)
            mlflow.log_param("features", ", ".join(FEATURE_NAMES))
            mlflow.log_param("train_rows", len(train))
            mlflow.log_param("data", "synthetic users (simulated)")
            mlflow.log_metrics(metrics)

            if metrics[f"ndcg_at_{K}"] > best_score:
                best_name, best_model, best_score = name, model, metrics[f"ndcg_at_{K}"]

    print("\nResults:")
    print(pd.DataFrame(results).T.round(3).to_string())

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, MODEL_PATH)  # the file the API loads
    MODEL_INFO_PATH.write_text(json.dumps(
        {"model": best_name, "features": FEATURE_NAMES, "metrics": results[best_name],
         "trained_on": "synthetic users (simulated)"}, indent=2))
    print(f"\nSaved best model ({best_name}) -> {MODEL_PATH}")
    print(f"MLflow runs are in {settings.mlflow_tracking_uri} (view with: mlflow ui)")


def rule_score_from_features(row):
    """The rule score, using feature values we already computed."""
    total = sum(RULE_WEIGHTS[name] * row[name] for name in RULE_WEIGHTS)
    return total / sum(RULE_WEIGHTS.values())


if __name__ == "__main__":
    main()
