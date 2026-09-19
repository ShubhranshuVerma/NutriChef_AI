"""The endpoints. Each one validates, calls a service, and returns the result.

Nothing is decided here - the services own the logic, and the deterministic
checks inside them own what is safe.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.api import schemas
from app.api.auth import current_user
from app.core.config import get_settings
from app.core.logging import get_logger
from app.ml.ranker import MODEL_PATH
from app.services import plan_service, planner, recipe_service

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1")

VERSION = "0.2.0"


def llm_ready():
    return get_settings().google_api_key is not None


def needs_llm():
    if not llm_ready():
        raise HTTPException(status_code=503, detail="The language model is not configured.")


def needs_data():
    if not planner.LIBRARY_PATH.exists():
        raise HTTPException(status_code=503, detail="The recipe library is not built yet.")


def saved_profile(user):
    """The signed-in user's saved preferences, or nothing when anonymous."""
    if user is None or user.profile is None:
        return None
    return user.profile.as_dict()


def merge(request: dict, profile: dict | None) -> dict:
    """Saved allergies and exclusions are added, never removed.

    The same rule as `agents.merge_with_profile`, applied to the plan endpoint:
    a request body cannot talk the API out of an allergy the person saved.
    """
    if not profile:
        return request
    merged = dict(request)
    merged["allergies"] = sorted(set(request.get("allergies", [])) | set(profile["allergies"]))
    merged["exclude"] = sorted(set(request.get("exclude", [])) | set(profile["exclude"]))
    for field in ["diet", "min_protein_g", "max_kcal", "max_cook_minutes"]:
        merged[field] = request.get(field) or profile.get(field)
    return merged


@router.post("/recipes/generate", responses={503: {"model": schemas.Error}})
def generate_recipe(body: schemas.RecipeRequest, user=Depends(current_user)):
    """Scenario 1: free text -> one recipe, checked by Python."""
    needs_llm()
    needs_data()
    profile = body.profile()
    saved = saved_profile(user)
    if saved:
        profile = merge(profile, saved)
    log.info("recipe request (%d chars, user=%s)", len(body.request), bool(user))
    return recipe_service.generate_recipe(body.request, profile=profile)


@router.post("/plans/generate", responses={503: {"model": schemas.Error}})
def generate_plan(body: schemas.PlanRequest, user=Depends(current_user)):
    """Scenario 2: a meal plan inside a budget, using what is already at home."""
    needs_data()
    constraints = body.constraints()
    if body.request:
        needs_llm()
        constraints = plan_service.constraints_from_text(body.request)

    saved = saved_profile(user)
    constraints = merge(constraints, saved)

    inventory = [item.model_dump() for item in body.inventory]
    if not inventory and user is not None:
        inventory = [item.as_dict() for item in user.inventory]

    log.info("plan request: %d days, budget %s, user=%s", body.days, body.budget_inr, bool(user))
    return plan_service.make_plan(constraints, days=body.days, slots=body.clean_slots(),
                                  budget_inr=body.budget_inr, inventory=inventory)


health_router = APIRouter()


@health_router.get("/health", response_model=schemas.Health)
def health():
    """What is ready. Never fails, so it is safe for a load balancer to poll."""
    settings = get_settings()
    return schemas.Health(
        status="ok", version=VERSION,
        recipes=planner.LIBRARY_PATH.exists(),
        ranking_model=MODEL_PATH.exists(),
        search_index=settings.chroma_dir.exists(),
        llm_configured=llm_ready(),
    )
