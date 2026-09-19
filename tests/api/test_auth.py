"""Accounts, profiles, inventory and feedback. A temporary database per test."""

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.api.main import create_app
from app.core import security
from app.core.config import get_settings
from app.database import session as db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 64)  # a realistic length, so pyjwt is happy
    get_settings.cache_clear()
    db.reset(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(routes, "llm_ready", lambda: True)
    monkeypatch.setattr(routes, "needs_data", lambda: None)
    yield TestClient(create_app(), raise_server_exceptions=False)
    db.reset(None)
    get_settings.cache_clear()


ACCOUNT = {"email": "Meena@Example.com", "password": "a-good-password"}


def token_of(client, account=ACCOUNT):
    response = client.post("/api/v1/auth/signup", json=account)
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# ---------- passwords ----------

def test_password_hash_is_not_the_password():
    hashed = security.hash_password("a-good-password")
    assert "a-good-password" not in hashed
    assert security.verify_password("a-good-password", hashed)
    assert not security.verify_password("nearly-right", hashed)


def test_two_users_with_the_same_password_get_different_hashes():
    assert security.hash_password("same-password") != security.hash_password("same-password")


# ---------- signup and login ----------

def test_signup_then_login(client):
    assert client.post("/api/v1/auth/signup", json=ACCOUNT).status_code == 201
    response = client.post("/api/v1/auth/login", json=ACCOUNT)
    assert response.status_code == 200
    assert security.read_token(response.json()["access_token"]) == 1


def test_email_is_stored_lowercase(client):
    token_of(client)
    response = client.post("/api/v1/auth/login",
                           json={"email": "meena@example.com", "password": ACCOUNT["password"]})
    assert response.status_code == 200


def test_duplicate_signup_is_refused(client):
    token_of(client)
    assert client.post("/api/v1/auth/signup", json=ACCOUNT).status_code == 409


def test_wrong_password_and_unknown_email_give_the_same_answer(client):
    token_of(client)
    wrong = client.post("/api/v1/auth/login", json={**ACCOUNT, "password": "wrong-password"})
    unknown = client.post("/api/v1/auth/login", json={"email": "nobody@example.com",
                                                      "password": "a-good-password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()  # no way to discover which emails exist


@pytest.mark.parametrize("body", [
    {"email": "not-an-email", "password": "a-good-password"},
    {"email": "a@b.com", "password": "short"},
    {"email": "a@b.com", "password": "x" * 73},
])
def test_bad_credentials_are_rejected(client, body):
    assert client.post("/api/v1/auth/signup", json=body).status_code == 422


def test_a_bad_token_is_simply_anonymous(client):
    response = client.get("/api/v1/users/me/profile",
                          headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


# ---------- profile ----------

def test_profile_round_trip(client):
    headers = token_of(client)
    assert client.get("/api/v1/users/me/profile", headers=headers).json()["allergies"] == []

    client.put("/api/v1/users/me/profile", headers=headers,
               json={"diet": "vegetarian", "allergies": ["soy", "invented"],
                     "exclude": ["whey"], "min_protein_g": 25})
    saved = client.get("/api/v1/users/me/profile", headers=headers).json()
    assert saved["diet"] == "vegetarian"
    assert saved["allergies"] == ["soy"]          # the invented one was dropped
    assert saved["exclude"] == ["whey"]
    assert saved["min_protein_g"] == 25


def test_profile_needs_an_account(client):
    assert client.get("/api/v1/users/me/profile").status_code == 401


# ---------- inventory ----------

def test_inventory_round_trip(client):
    headers = token_of(client)
    client.put("/api/v1/users/me/inventory", headers=headers,
               json=[{"ingredient_id": "paneer", "grams": 400, "expires_in_days": 2},
                     {"ingredient_id": "paneer", "grams": 999},
                     {"ingredient_id": "spinach", "grams": 250}])
    items = client.get("/api/v1/users/me/inventory", headers=headers).json()
    assert sorted(i["ingredient_id"] for i in items) == ["paneer", "spinach"]
    assert next(i for i in items if i["ingredient_id"] == "paneer")["grams"] == 400


# ---------- feedback ----------

def test_feedback_is_counted(client):
    headers = token_of(client)
    client.post("/api/v1/users/me/feedback", headers=headers,
                json={"recipe_id": "cur_1", "liked": True})
    response = client.post("/api/v1/users/me/feedback", headers=headers,
                           json={"recipe_id": "cur_2", "liked": False, "reason": "too oily"})
    assert response.status_code == 201
    assert response.json()["total"] == 2


# ---------- the part that matters: the profile reaches the endpoints ----------

def test_saved_allergies_are_added_to_a_plan_request(client, monkeypatch):
    headers = token_of(client)
    client.put("/api/v1/users/me/profile", headers=headers,
               json={"diet": "vegetarian", "allergies": ["soy"], "exclude": ["whey"]})

    seen = {}
    monkeypatch.setattr(routes.plan_service, "make_plan",
                        lambda request, **kwargs: seen.update(request=request, **kwargs) or {})
    client.post("/api/v1/plans/generate", headers=headers,
                json={"allergies": ["peanut"], "days": 2})

    assert seen["request"]["allergies"] == ["peanut", "soy"]   # union, never a replacement
    assert seen["request"]["exclude"] == ["whey"]
    assert seen["request"]["diet"] == "vegetarian"


def test_a_request_cannot_drop_a_saved_allergy(client, monkeypatch):
    headers = token_of(client)
    client.put("/api/v1/users/me/profile", headers=headers, json={"allergies": ["soy"]})

    seen = {}
    monkeypatch.setattr(routes.plan_service, "make_plan",
                        lambda request, **kwargs: seen.update(request=request) or {})
    client.post("/api/v1/plans/generate", headers=headers, json={"allergies": []})
    assert seen["request"]["allergies"] == ["soy"]


def test_the_saved_inventory_is_used_when_none_is_sent(client, monkeypatch):
    headers = token_of(client)
    client.put("/api/v1/users/me/inventory", headers=headers,
               json=[{"ingredient_id": "paneer", "grams": 400}])

    seen = {}
    monkeypatch.setattr(routes.plan_service, "make_plan",
                        lambda request, **kwargs: seen.update(kwargs) or {})
    client.post("/api/v1/plans/generate", headers=headers, json={"days": 2})
    assert seen["inventory"] == [{"ingredient_id": "paneer", "grams": 400,
                                  "expires_in_days": None}]


def test_anonymous_requests_still_work(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(routes.plan_service, "make_plan",
                        lambda request, **kwargs: seen.update(request=request, **kwargs) or {})
    response = client.post("/api/v1/plans/generate", json={"diet": "vegetarian", "days": 2})
    assert response.status_code == 200
    assert seen["inventory"] == []
