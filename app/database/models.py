"""The four tables. One file, no repository layer - the API talks to these directly.

A user's allergies and diet live here, so a request can never quietly drop them.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    profile: Mapped["Profile"] = relationship(back_populates="user", uselist=False,
                                              cascade="all, delete-orphan")
    inventory: Mapped[list["InventoryItem"]] = relationship(back_populates="user",
                                                            cascade="all, delete-orphan")
    feedback: Mapped[list["Feedback"]] = relationship(back_populates="user",
                                                      cascade="all, delete-orphan")


class Profile(Base):
    """Saved preferences. Semicolon-separated lists keep this readable in SQLite."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    diet: Mapped[str | None] = mapped_column(String(30))
    allergies: Mapped[str] = mapped_column(String(255), default="")
    exclude: Mapped[str] = mapped_column(String(500), default="")
    min_protein_g: Mapped[float | None] = mapped_column(Float)
    max_kcal: Mapped[float | None] = mapped_column(Float)
    max_cook_minutes: Mapped[int | None] = mapped_column(Integer)
    budget_per_meal_inr: Mapped[float | None] = mapped_column(Float)

    user: Mapped[User] = relationship(back_populates="profile")

    def as_dict(self):
        return {
            "diet": self.diet,
            "allergies": split(self.allergies),
            "exclude": split(self.exclude),
            "min_protein_g": self.min_protein_g,
            "max_kcal": self.max_kcal,
            "max_cook_minutes": self.max_cook_minutes,
            "budget_per_meal_inr": self.budget_per_meal_inr,
        }


class InventoryItem(Base):
    """What the person has at home, in the planner's own shape."""

    __tablename__ = "inventory"
    __table_args__ = (UniqueConstraint("user_id", "ingredient_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ingredient_id: Mapped[str] = mapped_column(String(50))
    grams: Mapped[float | None] = mapped_column(Float)
    expires_in_days: Mapped[int | None] = mapped_column(Integer)

    user: Mapped[User] = relationship(back_populates="inventory")

    def as_dict(self):
        return {"ingredient_id": self.ingredient_id, "grams": self.grams,
                "expires_in_days": self.expires_in_days}


class Feedback(Base):
    """One like or dislike. This is what turns the ranker personal over time."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    recipe_id: Mapped[str] = mapped_column(String(64))
    liked: Mapped[int] = mapped_column(Integer)  # 1 or 0
    reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    user: Mapped[User] = relationship(back_populates="feedback")


def split(text):
    return [part for part in (text or "").split(";") if part]


def join(items):
    return ";".join(items or [])
