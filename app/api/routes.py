"""The endpoints. Each one validates, calls a service, and returns the result.

Nothing is decided here - the services own the logic, and the deterministic
checks inside them own what is safe.
"""

from fastapi import APIRouter, HTTPException

from app.api import schemas
from app.core.config import get_settings
from app.core.logging import get_logger
from app.ml.ranker import MODEL_PATH
from app.services import plan_service, planner, recipe_service

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1")

VERSION = "0.1.0"


def llm_ready():
    return get_settings().google_api_key is not None


def needs_llm():
    if not llm_ready():
        raise HTTPException(status_code=503, detail="The language model is not configured.")


def needs_data():
    if not planner.LIBRARY_PATH.exists():
        raise HTTPException(status_code=503, detail="The recipe library is not built yet.")


@router.post("/recipes/generate", responses={503: {"model": schemas.Error}})
def generate_recipe(body: schemas.RecipeRequest):
    """Scenario 1: free text -> one recipe, checked by Python."""
    needs_llm()
    needs_data()
    log.info("recipe request (%d chars)", len(body.request))
    return recipe_service.generate_recipe(body.request, profile=body.profile())


@router.post("/plans/generate", responses={503: {"model": schemas.Error}})
def generate_plan(body: schemas.PlanRequest):
    """Scenario 2: a meal plan inside a budget, using what is already at home."""
    needs_data()
    constraints = body.constraints()
    if body.request:
        needs_llm()
        constraints = plan_service.constraints_from_text(body.request)
    log.info("plan request: %d days, budget %s", body.days, body.budget_inr)
    return plan_service.make_plan(
        constraints, days=body.days, slots=body.clean_slots(), budget_inr=body.budget_inr,
        inventory=[item.model_dump() for item in body.inventory],
    )


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
