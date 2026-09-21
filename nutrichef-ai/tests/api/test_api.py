"""API tests. No LLM and no data files - the services are replaced with fakes."""

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.api.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def ready(monkeypatch):
    """Pretend the library and the Gemini key are both there."""
    monkeypatch.setattr(routes, "llm_ready", lambda: True)
    monkeypatch.setattr(routes, "needs_data", lambda: None)


FAKE_RECIPE = {"status": "ok", "recipe": {"title": "Paneer Bhurji"}, "checks": {"passed": True}}
FAKE_PLAN = {"meals": [{"day": 1, "slot": "lunch", "title": "Dal Tadka"}],
             "totals": {"meals": 1}, "protein_target_met": True}


# ---------- health ----------

def test_health_always_answers(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body) == {"status", "version", "recipes", "ranking_model", "search_index",
                         "llm_configured"}


# ---------- recipes ----------

def test_generate_recipe(client, ready, monkeypatch):
    seen = {}

    def fake_generate(request_text, profile=None, deps=None):
        seen["text"], seen["profile"] = request_text, profile
        return FAKE_RECIPE

    monkeypatch.setattr(routes.recipe_service, "generate_recipe", fake_generate)
    response = client.post("/api/v1/recipes/generate",
                           json={"request": "high protein paneer dinner",
                                 "diet": "vegetarian", "allergies": ["soy"]})
    assert response.status_code == 200
    assert response.json()["recipe"]["title"] == "Paneer Bhurji"
    assert seen["profile"]["allergies"] == ["soy"]


def test_invented_allergen_is_dropped(client, ready, monkeypatch):
    seen = {}
    monkeypatch.setattr(routes.recipe_service, "generate_recipe",
                        lambda text, profile=None, deps=None: seen.update(profile) or FAKE_RECIPE)
    client.post("/api/v1/recipes/generate",
                json={"request": "dinner", "allergies": ["soy", "dragonfruit"]})
    assert seen["allergies"] == ["soy"]


@pytest.mark.parametrize("body", [
    {},                                   # no request at all
    {"request": "hi"},                    # too short
    {"request": "x" * 1001},              # too long
    {"request": "dinner", "allergies": ["a"] * 11},  # too many
])
def test_bad_input_is_rejected(client, ready, body):
    assert client.post("/api/v1/recipes/generate", json=body).status_code == 422


def test_no_llm_key_gives_503(client, monkeypatch):
    monkeypatch.setattr(routes, "llm_ready", lambda: False)
    response = client.post("/api/v1/recipes/generate", json={"request": "a dinner please"})
    assert response.status_code == 503
    assert "language model" in response.json()["detail"]


# ---------- plans ----------

def test_generate_plan_from_fields(client, ready, monkeypatch):
    seen = {}

    def fake_plan(request, **kwargs):
        seen.update({"request": request, **kwargs})
        return FAKE_PLAN

    monkeypatch.setattr(routes.plan_service, "make_plan", fake_plan)
    response = client.post("/api/v1/plans/generate", json={
        "diet": "vegetarian", "min_protein_g": 25, "days": 3, "budget_inr": 800,
        "inventory": [{"ingredient_id": "paneer", "grams": 400}],
    })
    assert response.status_code == 200
    assert seen["days"] == 3 and seen["budget_inr"] == 800
    assert seen["request"]["diet"] == "vegetarian"
    assert seen["inventory"][0]["ingredient_id"] == "paneer"


def test_plan_text_request_uses_the_llm(client, ready, monkeypatch):
    monkeypatch.setattr(routes.plan_service, "constraints_from_text",
                        lambda text: {"diet": "vegan"})
    monkeypatch.setattr(routes.plan_service, "make_plan",
                        lambda request, **kwargs: {**FAKE_PLAN, "constraints": request})
    response = client.post("/api/v1/plans/generate", json={"request": "vegan week under 1000"})
    assert response.json()["constraints"] == {"diet": "vegan"}


def test_plan_without_text_needs_no_llm(client, monkeypatch):
    monkeypatch.setattr(routes, "llm_ready", lambda: False)
    monkeypatch.setattr(routes, "needs_data", lambda: None)
    monkeypatch.setattr(routes.plan_service, "make_plan", lambda request, **kwargs: FAKE_PLAN)
    assert client.post("/api/v1/plans/generate", json={"diet": "vegetarian"}).status_code == 200


@pytest.mark.parametrize("body", [
    {"days": 0}, {"days": 15}, {"budget_inr": -5}, {"slots": []},
    {"inventory": [{"ingredient_id": "paneer", "grams": -1}]},
])
def test_bad_plan_input_is_rejected(client, ready, body):
    assert client.post("/api/v1/plans/generate", json=body).status_code == 422


def test_unknown_slot_is_ignored(client, ready, monkeypatch):
    seen = {}
    monkeypatch.setattr(routes.plan_service, "make_plan",
                        lambda request, **kwargs: seen.update(kwargs) or FAKE_PLAN)
    client.post("/api/v1/plans/generate", json={"slots": ["lunch", "elevenses"]})
    assert seen["slots"] == ["lunch"]


# ---------- errors ----------

def test_missing_library_gives_503(client, monkeypatch, tmp_path):
    monkeypatch.setattr(routes, "llm_ready", lambda: True)
    monkeypatch.setattr(routes.planner, "LIBRARY_PATH", tmp_path / "missing.jsonl")
    response = client.post("/api/v1/plans/generate", json={"diet": "vegetarian"})
    assert response.status_code == 503
    assert "library" in response.json()["detail"]


def test_internal_errors_do_not_leak(client, ready, monkeypatch, caplog):
    def explode(*args, **kwargs):
        raise RuntimeError("API key AIzaSecret leaked in this message")

    monkeypatch.setattr(routes.plan_service, "make_plan", explode)
    response = client.post("/api/v1/plans/generate", json={"diet": "vegetarian"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Something went wrong on our side."}
    assert "AIzaSecret" not in response.text
