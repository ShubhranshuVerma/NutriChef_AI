"""Train on a tiny made-up dataset to prove the training code runs."""

import pandas as pd
from sklearn.linear_model import LogisticRegression

from app.ml.features import FEATURE_NAMES
from scripts.train_ranker import ranking_scores, split_by_time


def fake_data(n_users=4, n_rows=10):
    rows = []
    for u in range(n_users):
        for step in range(n_rows):
            liked = step % 2
            features = [0.9 if liked else 0.1] * len(FEATURE_NAMES)
            rows.append([f"u{u}", f"r{step}", step, *features, liked])
    return pd.DataFrame(rows, columns=["user_id", "recipe_id", "step", *FEATURE_NAMES, "liked"])


def test_split_keeps_later_rows_for_testing():
    train, test = split_by_time(fake_data())
    assert len(train) == 32 and len(test) == 8
    assert train["step"].max() < test["step"].min()


def test_model_learns_the_obvious_pattern():
    train, test = split_by_time(fake_data())
    model = LogisticRegression(max_iter=1000).fit(train[FEATURE_NAMES], train["liked"])
    scores = model.predict_proba(test[FEATURE_NAMES])[:, 1]
    metrics = ranking_scores(test, scores)
    assert metrics["hit_rate_at_5"] == 1.0
    assert metrics["ndcg_at_5"] > 0.5
