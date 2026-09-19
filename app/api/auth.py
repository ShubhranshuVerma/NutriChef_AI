"""Signup, login, and "who is calling?".

The token is optional everywhere: without one the API still works, it just has
no saved profile to merge in.
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api import schemas
from app.core.security import create_token, hash_password, read_token, verify_password
from app.database.models import Profile, User
from app.database.session import get_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def current_user(authorization: str | None = Header(default=None),
                 session: Session = Depends(get_session)):
    """The logged-in user, or None. Never raises - anonymous use is allowed."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    user_id = read_token(authorization.split(" ", 1)[1].strip())
    return session.get(User, user_id) if user_id else None


def require_user(user=Depends(current_user)):
    """For the endpoints that genuinely need an account."""
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in first.")
    return user


@router.post("/signup", response_model=schemas.Token, status_code=201)
def signup(body: schemas.Credentials, session: Session = Depends(get_session)):
    email = body.email.strip().lower()
    if session.query(User).filter_by(email=email).first():
        raise HTTPException(status_code=409, detail="That email is already registered.")

    user = User(email=email, password_hash=hash_password(body.password))
    user.profile = Profile()
    session.add(user)
    session.commit()
    return schemas.Token(access_token=create_token(user.id))


@router.post("/login", response_model=schemas.Token)
def login(body: schemas.Credentials, session: Session = Depends(get_session)):
    user = session.query(User).filter_by(email=body.email.strip().lower()).first()
    # The same message either way, so this cannot be used to discover emails.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    return schemas.Token(access_token=create_token(user.id))
