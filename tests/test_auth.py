"""Accounts, tokens and saved preferences - and keeping secrets secret.

Each test gets its own empty database file.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import routes
from app.api.main import create_app
from app.core import security
from app.core.config import Settings, get_settings
from app.database import session as db

ACCOUNT = {"email": "Meena@Example.com", "password": "a-good-password"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 64)
    get_settings.cache_clear()
    db.reset(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(routes, "llm_ready", lambda: True)
    monkeypatch.setattr(routes, "needs_data", lambda: None)
    yield TestClient(create_app(), raise_server_exceptions=False)
    db.reset(None)
    get_settings.cache_clear()


def sign_up(client, account=ACCOUNT):
    response = client.post("/api/v1/auth/signup", json=account)
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def token_for_user_1(expires_in, secret):
    payload = {"sub": "1", "exp": datetime.now(timezone.utc) + expires_in}
    return jwt.encode(payload, secret, algorithm=security.ALGORITHM)


# ---------- passwords ----------

def test_a_stored_password_is_a_hash_not_the_password():
    hashed = security.hash_password("a-good-password")
    assert "a-good-password" not in hashed
    assert security.verify_password("a-good-password", hashed)
    assert not security.verify_password("nearly-right", hashed)


def test_a_password_bcrypt_would_quietly_cut_short_is_refused():
    """bcrypt ignores everything past 72 bytes. Matching our own message matters:
    bcrypt raises here too, and would otherwise pass this test for us."""
    with pytest.raises(ValueError, match="at most 72 bytes"):
        security.hash_password("p" * 73)


# ---------- signing up and in ----------

def test_sign_up_then_log_in(client):
    sign_up(client)
    response = client.post("/api/v1/auth/login",
                           json={"email": "meena@example.com", "password": "a-good-password"})
    assert response.status_code == 200                   # the email was stored in lowercase
    assert security.read_token(response.json()["access_token"]) == 1


def test_the_same_email_cannot_sign_up_twice(client):
    sign_up(client)
    assert client.post("/api/v1/auth/signup", json=ACCOUNT).status_code == 409


def test_a_wrong_password_and_an_unknown_email_look_the_same(client):
    """Otherwise anyone could find out which emails have accounts."""
    sign_up(client)
    wrong = client.post("/api/v1/auth/login", json={**ACCOUNT, "password": "wrong-password"})
    unknown = client.post("/api/v1/auth/login",
                          json={"email": "nobody@example.com", "password": "a-good-password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


# ---------- tokens ----------

def test_an_expired_token_is_refused(client):
    sign_up(client)                                       # so user 1 really exists
    expired = token_for_user_1(timedelta(minutes=-1), get_settings().jwt_secret_key.get_secret_value())
    response = client.get("/api/v1/users/me/profile", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_a_token_signed_with_another_secret_is_refused(client):
    sign_up(client)
    forged = token_for_user_1(timedelta(hours=1), "a-secret-that-is-not-ours-at-all")
    response = client.get("/api/v1/users/me/profile", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


# ---------- saved preferences ----------

def test_a_saved_profile_comes_back(client):
    headers = sign_up(client)
    client.put("/api/v1/users/me/profile", headers=headers,
               json={"diet": "vegetarian", "allergies": ["soy", "invented"], "min_protein_g": 25})
    saved = client.get("/api/v1/users/me/profile", headers=headers).json()
    assert saved["diet"] == "vegetarian"
    assert saved["allergies"] == ["soy"]                  # the invented one was dropped


def test_saved_allergies_are_added_to_a_plan_request(client, monkeypatch):
    headers = sign_up(client)
    client.put("/api/v1/users/me/profile", headers=headers,
               json={"allergies": ["soy"], "exclude": ["whey"]})
    seen = {}
    monkeypatch.setattr(routes.planner, "make_plan",
                        lambda request, **options: seen.update(request=request) or {})

    client.post("/api/v1/plans/generate", headers=headers, json={"allergies": ["peanut"]})
    assert seen["request"]["allergies"] == ["peanut", "soy"]   # added, never replaced
    assert seen["request"]["exclude"] == ["whey"]


def test_a_request_cannot_drop_a_saved_allergy(client, monkeypatch):
    headers = sign_up(client)
    client.put("/api/v1/users/me/profile", headers=headers, json={"allergies": ["soy"]})
    seen = {}
    monkeypatch.setattr(routes.planner, "make_plan",
                        lambda request, **options: seen.update(request=request) or {})

    client.post("/api/v1/plans/generate", headers=headers, json={"allergies": []})
    assert seen["request"]["allergies"] == ["soy"]


def test_the_saved_kitchen_is_used_when_the_request_sends_none(client, monkeypatch):
    headers = sign_up(client)
    client.put("/api/v1/users/me/inventory", headers=headers,
               json=[{"ingredient_id": "paneer", "grams": 400}])
    seen = {}
    monkeypatch.setattr(routes.planner, "make_plan",
                        lambda request, **options: seen.update(options) or {})

    client.post("/api/v1/plans/generate", headers=headers, json={"days": 2})
    assert seen["inventory"][0]["ingredient_id"] == "paneer"


def test_likes_and_dislikes_reach_the_planner(client, monkeypatch):
    headers = sign_up(client)
    client.post("/api/v1/users/me/feedback", headers=headers, json={"recipe_id": "r1", "liked": True})
    client.post("/api/v1/users/me/feedback", headers=headers, json={"recipe_id": "r2", "liked": False})
    seen = {}
    monkeypatch.setattr(routes.planner, "make_plan",
                        lambda request, **options: seen.update(options) or {})

    client.post("/api/v1/plans/generate", headers=headers, json={"days": 2})
    assert seen["feedback"] == {"liked": ["r1"], "disliked": ["r2"]}


# ---------- secrets ----------

def test_the_gemini_key_is_never_printed(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaFAKEKEY1234567890abcdefgh")
    settings = Settings()
    assert "AIzaFAKE" not in repr(settings)
    assert settings.google_api_key.get_secret_value().startswith("AIza")


def test_production_refuses_the_placeholder_jwt_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaFAKEKEY1234567890abcdefgh")
    monkeypatch.setenv("JWT_SECRET_KEY", "change-me")
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings()
