"""The four LLM agents. Each one is a function: build a prompt, call the LLM,
check the answer with Pydantic.

Nothing here decides what is safe - that is the job of app/validation.
"""

import json
import re

from pydantic import ValidationError

from app.agents import prompts
from app.core.llm import answer_text, invoke_with_retry
from app.core.logging import get_logger
from app.agents.schemas import ALLERGENS, DIETS, Constraints, Critique, RecipeDraft

log = get_logger(__name__)

MAX_REQUEST_LENGTH = 1000


def parse_json(text):
    """Read the JSON out of an LLM answer, even if it is wrapped in ```json fences."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON found in the answer: {text[:200]}")
    return json.loads(text[start : end + 1])



def ask(llm, prompt, model, retries=1):
    """Call the LLM and turn the answer into `model`. Retries once if it is malformed."""
    for attempt in range(retries + 1):
        text = answer_text(invoke_with_retry(llm, prompt))
        try:
            return model(**parse_json(text))
        except (ValueError, ValidationError, TypeError) as error:
            log.warning("Bad answer from the LLM (attempt %d): %s", attempt + 1, error)
            if attempt == retries:
                raise
            prompt = f"{prompt}\n\nYour last answer was not valid: {error}\nAnswer with JSON only."
    raise RuntimeError("unreachable")


# ---------- 1. requirements ----------

def extract_requirements(request_text, llm):
    """Free text -> Constraints."""
    text = str(request_text)[:MAX_REQUEST_LENGTH]
    constraints = ask(llm, prompts.REQUIREMENTS_PROMPT.format(request=text), Constraints)
    return clean_constraints(constraints)


def clean_constraints(constraints):
    """Drop anything the LLM invented that is not on our lists."""
    if constraints.diet not in DIETS:
        constraints.diet = None
    constraints.allergies = [a for a in constraints.allergies if a in ALLERGENS]
    return constraints


def merge_with_profile(constraints, profile):
    """Combine the request with the saved profile.

    Allergies and exclusions are only ever ADDED - a request can never remove
    an allergy the person saved earlier.
    """
    if not profile:
        return constraints
    merged = constraints.model_copy(deep=True)
    merged.allergies = sorted(set(merged.allergies) | set(profile.get("allergies", [])))
    merged.exclude = sorted(set(merged.exclude) | set(profile.get("exclude", [])))
    merged.diet = merged.diet or profile.get("diet")
    for field in ["cuisine", "max_kcal", "min_protein_g", "max_cook_minutes", "max_cost_inr"]:
        if getattr(merged, field) is None and profile.get(field) is not None:
            setattr(merged, field, profile[field])
    return merged


# ---------- 2. recipe ----------

def generate_recipe(constraints, context, llm):
    """Constraints + similar recipes -> a new recipe."""
    prompt = prompts.RECIPE_PROMPT.format(
        constraints=describe_constraints(constraints),
        context=context or "(nothing found)",
    )
    return ask(llm, prompt, RecipeDraft)


# ---------- 3. critic ----------

def critique_recipe(constraints, recipe, report, llm):
    prompt = prompts.CRITIC_PROMPT.format(
        constraints=describe_constraints(constraints),
        recipe=describe_recipe(recipe),
        report=json.dumps(report, indent=2, default=str),
    )
    return ask(llm, prompt, Critique)


# ---------- 4. revision ----------

def revise_recipe(constraints, recipe, critique, llm):
    prompt = prompts.REVISION_PROMPT.format(
        constraints=describe_constraints(constraints),
        recipe=describe_recipe(recipe),
        problems="\n".join(f"- {p}" for p in critique.problems) or "- none",
        suggestions="\n".join(f"- {s}" for s in critique.suggestions) or "- none",
    )
    return ask(llm, prompt, RecipeDraft)


# ---------- helpers ----------

# Field names alone were being misread - the critic treated "have_ingredients"
# as a list of ingredients the recipe MUST contain.
LABELS = {
    "diet": "diet (a hard rule)",
    "allergies": "allergic to (never use, in any form)",
    "exclude": "does not want",
    "have_ingredients": "already has at home (nice to use, NOT required)",
    "max_kcal": "at most this many kcal per serving",
    "min_protein_g": "at least this much protein per serving (g)",
    "max_cook_minutes": "at most this many minutes",
    "max_cost_inr": "at most this many rupees per serving",
}


def describe_constraints(constraints):
    """Constraints as short labelled lines, so prompts stay readable and unambiguous."""
    lines = []
    for key, value in constraints.model_dump().items():
        if value in (None, [], ""):
            continue
        text = ", ".join(map(str, value)) if isinstance(value, list) else value
        lines.append(f"- {LABELS.get(key, key)}: {text}")
    return "\n".join(lines) or "- no special requirements"


def describe_recipe(recipe):
    """Works with a RecipeDraft or with our recipe dicts (which call steps 'directions')."""
    if isinstance(recipe, RecipeDraft):
        recipe = recipe.model_dump()
    lines = []
    for item in recipe["ingredients"]:
        lines.append(f"- {item['raw'] if isinstance(item, dict) else item}")
    steps = recipe.get("steps") or recipe.get("directions", [])
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    return f"{recipe['title']} (serves {recipe['servings']})\n" + "\n".join(lines) + f"\n{numbered}"


def format_context(hits, limit=3):
    """Turn RAG search results into text for the recipe prompt."""
    parts = []
    for hit in hits[:limit]:
        source = hit.get("metadata", {}).get("source_url", "")
        parts.append(hit["text"] + (f"\n(source: {source})" if source else ""))
    return "\n\n---\n\n".join(parts)
