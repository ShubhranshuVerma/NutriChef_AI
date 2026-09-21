"""Train the recipe ranking model and log the run to MLflow.

Run from the project root (after scripts.simulate_users):
    python -m scripts.train_ranker

Saves the better model to ml/artifacts/ranker.joblib
"""

import json
import os

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import joblib
import mlflow
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.core.config import PROJECT_ROOT, get_settings
from app.ml.features import FEATURE_NAMES, feature_row
from app.ml.ranker import MODEL_INFO_PATH, MODEL_PATH, RULE_WEIGHTS
from ml.evaluation.metrics import average_metrics
from scripts.simulate_users import INTERACTIONS_PATH, USERS_PATH
from scripts.tag_recipes import OUTPUT_PATH as TAGGED_PATH

TEST_SHARE = 0.2  # each user's last 20% of interactions are the test set
K = 5


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
    for path in (USERS_PATH, INTERACTIONS_PATH, TAGGED_PATH):
        if not path.exists():
            print(f"Missing {path.name}. Run scripts.tag_recipes and scripts.simulate_users first.")
            return

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
