"""What the LLM is allowed to return. Pydantic rejects anything else."""

from pydantic import BaseModel, Field

DIETS = ["vegan", "vegetarian", "eggetarian", "pescatarian", "jain", "non_vegetarian"]
ALLERGENS = ["milk", "egg", "fish", "crustacean", "tree_nut", "peanut", "wheat_gluten",
             "soy", "sesame", "sulphite"]


class Constraints(BaseModel):
    """What the user asked for, in a structured form."""

    diet: str | None = None
    allergies: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    have_ingredients: list[str] = Field(default_factory=list)
    course: str | None = None  # main, breakfast, snack, side, dessert, beverage
    cuisine: str | None = None
    max_kcal: int | None = None
    min_protein_g: int | None = None
    max_cook_minutes: int | None = None
    max_cost_inr: int | None = None
    servings: int | None = None
    notes: str = ""


class RecipeDraft(BaseModel):
    """A recipe written by the LLM. Quantities must be in grams or millilitres."""

    title: str
    servings: int = Field(ge=1, le=12)
    ingredients: list[str] = Field(min_length=2)  # e.g. "200 g paneer"
    steps: list[str] = Field(min_length=1)
    notes: str = ""


class Critique(BaseModel):
    """What the critic thinks is wrong with a recipe."""

    problems: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    @property
    def needs_revision(self):
        return bool(self.problems)
