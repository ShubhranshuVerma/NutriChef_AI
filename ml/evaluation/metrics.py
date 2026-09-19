"""Ranking metrics. Each function takes the recipe ids we recommended (in order)
and the set of recipes the user actually liked."""

import math


def precision_at_k(recommended, liked, k=5):
    top = recommended[:k]
    return sum(1 for r in top if r in liked) / k if top else 0.0


def recall_at_k(recommended, liked, k=5):
    if not liked:
        return 0.0
    top = recommended[:k]
    return sum(1 for r in top if r in liked) / len(liked)


def hit_rate_at_k(recommended, liked, k=5):
    return 1.0 if any(r in liked for r in recommended[:k]) else 0.0


def ndcg_at_k(recommended, liked, k=5):
    """Rewards liked recipes that appear near the top of the list."""
    gain = sum(1 / math.log2(i + 2) for i, r in enumerate(recommended[:k]) if r in liked)
    best = sum(1 / math.log2(i + 2) for i in range(min(len(liked), k)))
    return gain / best if best else 0.0


def average_metrics(results, k=5):
    """results: list of (recommended_ids, liked_ids) per user."""
    if not results:
        return {}
    return {
        f"precision_at_{k}": sum(precision_at_k(r, l, k) for r, l in results) / len(results),
        f"recall_at_{k}": sum(recall_at_k(r, l, k) for r, l in results) / len(results),
        f"hit_rate_at_{k}": sum(hit_rate_at_k(r, l, k) for r, l in results) / len(results),
        f"ndcg_at_{k}": sum(ndcg_at_k(r, l, k) for r, l in results) / len(results),
    }
