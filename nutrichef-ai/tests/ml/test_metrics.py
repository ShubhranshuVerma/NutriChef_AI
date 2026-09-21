from ml.evaluation.metrics import (
    average_metrics,
    hit_rate_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)

RECOMMENDED = ["a", "b", "c", "d", "e"]
LIKED = {"b", "e", "z"}


def test_precision_and_recall():
    assert precision_at_k(RECOMMENDED, LIKED, k=5) == 2 / 5
    assert recall_at_k(RECOMMENDED, LIKED, k=5) == 2 / 3
    assert precision_at_k(RECOMMENDED, LIKED, k=1) == 0.0


def test_hit_rate():
    assert hit_rate_at_k(RECOMMENDED, LIKED, k=5) == 1.0
    assert hit_rate_at_k(RECOMMENDED, LIKED, k=1) == 0.0


def test_ndcg_rewards_higher_positions():
    top = ndcg_at_k(["b", "e", "x"], {"b", "e"}, k=3)
    bottom = ndcg_at_k(["x", "b", "e"], {"b", "e"}, k=3)
    assert top == 1.0
    assert bottom < top


def test_empty_cases():
    assert precision_at_k([], {"a"}) == 0.0
    assert recall_at_k(RECOMMENDED, set()) == 0.0
    assert ndcg_at_k(RECOMMENDED, set()) == 0.0
    assert average_metrics([]) == {}


def test_average_metrics():
    results = [(RECOMMENDED, LIKED), (["b", "e", "a"], {"b"})]
    averages = average_metrics(results, k=5)
    assert set(averages) == {"precision_at_5", "recall_at_5", "hit_rate_at_5", "ndcg_at_5"}
    assert 0 <= averages["ndcg_at_5"] <= 1
