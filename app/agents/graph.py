"""The recipe workflow, built with LangGraph.

understand -> search -> write -> check -> (clean? finish : critique -> revise -> check ...)

The LLM writes and rewrites. Nutrition, the safety checks and the critique are
plain Python, and a recipe that breaks a hard rule is never returned as "ok".
"""

import time

from langgraph.graph import END, StateGraph

from app.agents import agents
from app.core.logging import get_logger
from app.nutrition.calculator import calculate_recipe
from app.nutrition.parsing import parse_ingredient
from app.nutrition.checks import check_recipe, tag_recipe

log = get_logger(__name__)

MAX_REVISIONS = 2


# ---------- helpers ----------

def draft_to_recipe(draft, tables):
    """RecipeDraft -> the recipe dict the rest of the code uses."""
    ingredients = []
    for line in draft.ingredients:
        item = parse_ingredient(line)
        ingredients.append({
            "raw": line, "name": item.name, "quantity": item.quantity, "unit": item.unit,
            "ingredient_id": tables["matcher"].match(item.name),
        })
    return {
        "title": draft.title, "servings": draft.servings, "ingredients": ingredients,
        "directions": list(draft.steps), "origin": "generated", "notes": draft.notes,
    }


def request_from_constraints(constraints):
    """Constraints -> the request dict that check_recipe expects."""
    return {
        "allergies": constraints.allergies, "exclude": constraints.exclude,
        "diet": constraints.diet, "max_kcal": constraints.max_kcal,
        "min_protein_g": constraints.min_protein_g,
        "max_cook_minutes": constraints.max_cook_minutes,
        "max_cost_inr": constraints.max_cost_inr,
    }


def evaluate(draft, constraints, deps):
    """Nutrition + tags + checks for one draft. No LLM involved."""
    recipe = draft_to_recipe(draft, deps["tables"])
    nutrition = calculate_recipe(recipe["ingredients"], deps["tables"], draft.servings,
                                 constraints.course or "main")
    recipe.update(nutrition["per_serving"])
    recipe["cost_per_serving_inr"] = nutrition["cost_inr_per_serving"]
    recipe["nutrition_confidence"] = nutrition["confidence"]

    recipe = tag_recipe(recipe, deps["rules"])
    checks = check_recipe(recipe, request_from_constraints(constraints), deps["rules"])
    return recipe, nutrition, checks


# ---------- the steps ----------

def make_nodes(deps):
    llm = deps["llm"]

    def note(state, step, detail=""):
        state["trace"].append({"step": step, "detail": detail,
                               "seconds": round(time.perf_counter() - state["started"], 2)})

    def understand(state):
        constraints = agents.extract_requirements(state["request_text"], llm)
        state["constraints"] = agents.merge_with_profile(constraints, state.get("profile"))
        note(state, "understand", agents.describe_constraints(state["constraints"]))
        return state

    def search(state):
        search_recipes = deps.get("search_recipes")
        if search_recipes is None:
            state["context"] = ""
            note(state, "search", "skipped (no search index)")
            return state
        constraints = state["constraints"]
        query = f"{constraints.course or 'dinner'} with {', '.join(constraints.have_ingredients)}"
        hits = search_recipes(query, diet=constraints.diet,
                              avoid_allergens=constraints.allergies,
                              max_kcal=constraints.max_kcal)
        state["context"] = agents.format_context(hits)
        state["sources"] = [h["metadata"].get("source_url", "") for h in hits[:3]]
        note(state, "search", f"{len(hits)} similar recipes")
        return state

    def write(state):
        draft = agents.generate_recipe(state["constraints"], state["context"], llm)
        state["draft"] = draft
        note(state, "write", draft.title)
        return state

    def check(state):
        recipe, nutrition, checks = evaluate(state["draft"], state["constraints"], deps)
        state.update({"recipe": recipe, "nutrition": nutrition, "checks": checks})
        note(state, "check", "passed" if checks["passed"] else "; ".join(checks["failures"]))
        return state

    def critique(state):
        state["critique"] = agents.critique_recipe(state["checks"])
        note(state, "critique", "; ".join(state["critique"].problems) or "no problems")
        return state

    def revise(state):
        state["revisions"] += 1
        state["draft"] = agents.revise_recipe(state["constraints"], state["recipe"],
                                              state["critique"], llm)
        note(state, f"revise {state['revisions']}", state["draft"].title)
        return state

    def finish(state):
        state["status"] = "ok" if state["checks"]["passed"] else "failed"
        note(state, "finish", state["status"])
        return state

    return {"understand": understand, "search": search, "write": write, "check": check,
            "critique": critique, "revise": revise, "finish": finish}


def needs_critique(state):
    """A draft that passes every rule with no warnings is finished; anything else is fixed."""
    checks = state["checks"]
    if checks["passed"] and not checks["warnings"]:
        return "finish"
    return "critique"


def needs_revision(state):
    """Decide what happens after the critic: revise again, or stop."""
    if state["critique"].problems and state["revisions"] < MAX_REVISIONS:
        return "revise"
    return "finish"


def build_graph(deps):
    """deps: llm, tables, rules and (optionally) search_recipes."""
    nodes = make_nodes(deps)
    graph = StateGraph(dict)
    for name, function in nodes.items():
        graph.add_node(name, function)

    graph.set_entry_point("understand")
    graph.add_edge("understand", "search")
    graph.add_edge("search", "write")
    graph.add_edge("write", "check")
    graph.add_conditional_edges("check", needs_critique,
                                {"critique": "critique", "finish": "finish"})
    graph.add_conditional_edges("critique", needs_revision,
                                {"revise": "revise", "finish": "finish"})
    graph.add_edge("revise", "check")
    graph.add_edge("finish", END)
    return graph.compile()


def run(request_text, deps, profile=None):
    """Run the whole workflow once and return the final state."""
    graph = build_graph(deps)
    state = {"request_text": request_text, "profile": profile, "revisions": 0,
             "trace": [], "started": time.perf_counter(), "context": "", "sources": []}
    return graph.invoke(state)
