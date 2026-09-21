"""Loads everything the workflow needs once, then runs it.

The API (Phase 13) and the demo script both use `generate_recipe`.
"""

from functools import lru_cache

from app.agents import graph
from app.core.llm import get_llm
from app.nutrition.calculator import load_tables
from app.agents import rag
from app.nutrition.checks import load_rules


@lru_cache(maxsize=1)
def load_dependencies(use_search=True):
    """Tables, rules, the LLM and (optionally) the search index."""
    deps = {"tables": load_tables(), "rules": load_rules(), "llm": get_llm()}
    if use_search and rag.get_settings().chroma_dir.exists():
        embeddings = rag.get_embeddings()
        deps["search_recipes"] = lambda query, **filters: rag.search_recipes(
            query, k=3, embeddings=embeddings, **filters
        )
    return deps


def generate_recipe(request_text, profile=None, deps=None):
    """Run the workflow and return a tidy result."""
    deps = deps or load_dependencies()
    state = graph.run(request_text, deps, profile)
    return build_result(state)


def build_result(state):
    recipe = state.get("recipe", {})
    nutrition = state.get("nutrition", {})
    return {
        "status": state.get("status", "failed"),
        "recipe": {
            "title": recipe.get("title"),
            "servings": recipe.get("servings"),
            "ingredients": [i["raw"] for i in recipe.get("ingredients", [])],
            "steps": recipe.get("directions", []),
            "allergens": recipe.get("allergens", []),
            "suitable_diets": recipe.get("suitable_diets", []),
        },
        "nutrition_per_serving": nutrition.get("per_serving", {}),
        "cost_per_serving_inr": nutrition.get("cost_inr_per_serving"),
        "nutrition_confidence": nutrition.get("confidence"),
        "checks": state.get("checks", {}),
        "revisions": state.get("revisions", 0),
        "sources": [s for s in state.get("sources", []) if s],
        "trace": state.get("trace", []),
        "disclaimer": (
            "Nutrition values are estimates. NutriChef is a general wellness tool, not medical "
            "advice, and cannot guarantee allergy safety - always check ingredient labels."
        ),
    }
