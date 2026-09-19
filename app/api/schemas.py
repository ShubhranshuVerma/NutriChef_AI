"""Request and response models for the API.

These are the only shapes the API accepts. Anything else is rejected by
FastAPI with a 422 before our code runs - that is the input validation.
"""

from pydantic import BaseModel, Field

from app.schemas.recipe import ALLERGENS, DIETS
from app.services.planner import COURSE_FOR_SLOT

MAX_TEXT = 1000


class RecipeRequest(BaseModel):
    request: str = Field(min_length=3, max_length=MAX_TEXT,
                         examples=["vegetarian high-protein dinner under 600 calories"])
    diet: str | None = Field(default=None, examples=["vegetarian"])
    allergies: list[str] = Field(default_factory=list, max_length=10, examples=[["soy"]])
    exclude: list[str] = Field(default_factory=list, max_length=20)

    def profile(self):
        """The saved-profile part: allergies and diet can only be added to."""
        return {"diet": self.diet,
                "allergies": [a for a in self.allergies if a in ALLERGENS],
                "exclude": [e[:50] for e in self.exclude]}


class InventoryItem(BaseModel):
    ingredient_id: str = Field(max_length=50, examples=["paneer"])
    grams: float | None = Field(default=None, ge=0, le=100_000)
    expires_in_days: int | None = Field(default=None, ge=0, le=365)


class PlanRequest(BaseModel):
    """Either give `request` (parsed by the LLM) or the fields directly."""

    request: str | None = Field(default=None, max_length=MAX_TEXT)
    diet: str | None = None
    allergies: list[str] = Field(default_factory=list, max_length=10)
    exclude: list[str] = Field(default_factory=list, max_length=20)
    min_protein_g: float | None = Field(default=None, ge=0, le=300)
    max_kcal: float | None = Field(default=None, ge=0, le=5000)
    max_cook_minutes: int | None = Field(default=None, ge=0, le=600)

    days: int = Field(default=7, ge=1, le=14)
    slots: list[str] = Field(default_factory=lambda: ["breakfast", "lunch", "dinner"],
                             min_length=1, max_length=6)
    budget_inr: float | None = Field(default=None, gt=0, le=1_000_000)
    inventory: list[InventoryItem] = Field(default_factory=list, max_length=100)

    def constraints(self):
        """The fields as the request dict the checks use."""
        return {"diet": self.diet if self.diet in DIETS else None,
                "allergies": [a for a in self.allergies if a in ALLERGENS],
                "exclude": [e[:50] for e in self.exclude],
                "min_protein_g": self.min_protein_g, "max_kcal": self.max_kcal,
                "max_cook_minutes": self.max_cook_minutes}

    def clean_slots(self):
        return [s for s in self.slots if s in COURSE_FOR_SLOT] or ["breakfast", "lunch", "dinner"]


class Health(BaseModel):
    status: str
    version: str
    recipes: bool
    ranking_model: bool
    search_index: bool
    llm_configured: bool


class Error(BaseModel):
    detail: str
