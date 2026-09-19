"""Meal planning as one call, for the API and the demo script.

The LLM (optional) only turns free text into constraints. Everything after that
is the deterministic planner.
"""

from app.agents.agents import extract_requirements
from app.core.llm import get_llm
from app.services import planner

DAILY_KCAL = 2000  # a normal day, used only to aim for sensibly sized meals


def constraints_from_text(text):
    """Free text -> the request dict the checks use. Needs a Gemini key."""
    constraints = extract_requirements(text, get_llm())
    return {"diet": constraints.diet, "allergies": constraints.allergies,
            "exclude": constraints.exclude, "min_protein_g": constraints.min_protein_g,
            "max_kcal": constraints.max_kcal, "max_cook_minutes": constraints.max_cook_minutes}


def user_profile(request, budget_inr, days, slots):
    """What the ranker uses. Without a calorie limit we aim for a normal-sized day."""
    meals_per_day = len(slots) or 1
    return {
        "diet": request.get("diet"),
        "protein_target_g": request.get("min_protein_g"),
        "kcal_target": request.get("max_kcal") or round(DAILY_KCAL / meals_per_day),
        "budget_per_meal_inr": (round(budget_inr / (days * meals_per_day), 2)
                                if budget_inr else None),
        "max_cook_minutes": request.get("max_cook_minutes"),
    }


def make_plan(request, days=7, slots=None, budget_inr=None, inventory=None, deps=None):
    """request: the constraints dict. Returns the plan plus a protein summary."""
    deps = deps or planner.load_dependencies()
    slots = slots or planner.DEFAULT_SLOTS
    profile = user_profile(request, budget_inr, days, slots)

    plan = planner.make_plan(deps["recipes"], profile, request, deps["rules"], deps["tables"],
                             days=days, slots=slots, budget_inr=budget_inr, inventory=inventory)

    plan["constraints"] = request
    plan["protein_target_per_day_g"] = (request["min_protein_g"] * len(slots)
                                        if request.get("min_protein_g") else None)
    plan["protein_target_met"] = (
        plan["protein_target_per_day_g"] is None
        or plan["totals"]["avg_protein_per_day"] >= plan["protein_target_per_day_g"]
    )
    plan["disclaimer"] = (
        "Nutrition values and prices are estimates. NutriChef is a general wellness tool, not "
        "medical advice, and cannot guarantee allergy safety - always check ingredient labels."
    )
    return plan
