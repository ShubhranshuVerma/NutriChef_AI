"""The logged-in user's profile, inventory and feedback."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import schemas
from app.api.auth import require_user
from app.database.models import Feedback, InventoryItem, Profile, join
from app.database.session import get_session

router = APIRouter(prefix="/api/v1/users/me", tags=["me"])


def profile_of(user, session):
    if user.profile is None:
        user.profile = Profile()
        session.commit()
    return user.profile


@router.get("/profile", response_model=schemas.ProfileOut)
def get_profile(user=Depends(require_user), session: Session = Depends(get_session)):
    return profile_of(user, session).as_dict()


@router.put("/profile", response_model=schemas.ProfileOut)
def put_profile(body: schemas.ProfileIn, user=Depends(require_user),
                session: Session = Depends(get_session)):
    profile = profile_of(user, session)
    profile.diet = body.clean_diet()
    profile.allergies = join(body.clean_allergies())
    profile.exclude = join(body.exclude)
    profile.min_protein_g = body.min_protein_g
    profile.max_kcal = body.max_kcal
    profile.max_cook_minutes = body.max_cook_minutes
    profile.budget_per_meal_inr = body.budget_per_meal_inr
    session.commit()
    return profile.as_dict()


@router.get("/inventory", response_model=list[schemas.InventoryItem])
def get_inventory(user=Depends(require_user)):
    return [item.as_dict() for item in user.inventory]


@router.put("/inventory", response_model=list[schemas.InventoryItem])
def put_inventory(body: list[schemas.InventoryItem], user=Depends(require_user),
                  session: Session = Depends(get_session)):
    """Replaces the whole list - simpler than per-item edits, and it is a small list."""
    session.query(InventoryItem).filter_by(user_id=user.id).delete()
    seen = set()
    for item in body:
        if item.ingredient_id in seen:
            continue  # the table has a unique constraint; keep the first one
        seen.add(item.ingredient_id)
        session.add(InventoryItem(user_id=user.id, **item.model_dump()))
    session.commit()
    session.refresh(user)
    return [item.as_dict() for item in user.inventory]


@router.post("/feedback", status_code=201)
def add_feedback(body: schemas.FeedbackIn, user=Depends(require_user),
                 session: Session = Depends(get_session)):
    session.add(Feedback(user_id=user.id, recipe_id=body.recipe_id,
                         liked=int(body.liked), reason=body.reason))
    session.commit()
    return {"saved": True, "total": session.query(Feedback).filter_by(user_id=user.id).count()}
