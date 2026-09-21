"""The API and the website it serves. The services are replaced with fakes."""

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.api.main import create_app
from app.core.llm import QuotaExhausted

FAKE_RECIPE = {"status": "ok", "recipe": {"title": "Paneer Bhurji"}, "checks": {"passed": True}}
FAKE_PLAN = {"meals": [{"day": 1, "slot": "lunch", "title": "Dal Tadka"}],
             "totals": {"meals": 1}, "protein_target_met": True}


@pytest.fixture
def client():
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def ready(monkeypatch):
    """Pretend the recipe library and the Gemini key are both there."""
    monkeypatch.setattr(routes, "llm_ready", lambda: True)
    monkeypatch.setattr(routes, "needs_data", lambda: None)


def test_health_always_answers(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert set(body) == {"status", "version", "recipes", "ranking_model", "search_index",
                         "llm_configured"}


def test_a_recipe_request_reaches_the_workflow(client, ready, monkeypatch):
    seen = {}

    def fake_generate(request_text, profile=None, deps=None):
        seen["profile"] = profile
        return FAKE_RECIPE

    monkeypatch.setattr(routes.recipe_service, "generate_recipe", fake_generate)
    response = client.post("/api/v1/recipes/generate",
                           json={"request": "high protein paneer dinner",
                                 "allergies": ["soy", "dragonfruit"]})
    assert response.status_code == 200
    assert response.json()["recipe"]["title"] == "Paneer Bhurji"
    assert seen["profile"]["allergies"] == ["soy"]          # the invented allergen was dropped


def test_a_plan_request_reaches_the_planner(client, ready, monkeypatch):
    seen = {}

    def fake_plan(request, **options):
        seen.update(request=request, **options)
        return FAKE_PLAN

    monkeypatch.setattr(routes.planner, "make_plan", fake_plan)
    response = client.post("/api/v1/plans/generate", json={
        "diet": "vegetarian", "days": 3, "budget_inr": 800,
        "inventory": [{"ingredient_id": "paneer", "grams": 400}]})
    assert response.status_code == 200
    assert seen["days"] == 3 and seen["budget_inr"] == 800
    assert seen["request"]["diet"] == "vegetarian"


def test_a_plan_in_plain_words_needs_no_gemini_key(client, ready, monkeypatch):
    seen = {}
    monkeypatch.setattr(routes, "llm_ready", lambda: False)
    monkeypatch.setattr(routes.planner, "make_plan",
                        lambda request, **options: seen.update(request=request) or FAKE_PLAN)
    response = client.post("/api/v1/plans/generate",
                           json={"request": "vegetarian, allergic to soy, high protein"})
    assert response.status_code == 200
    assert seen["request"]["allergies"] == ["soy"]
    assert seen["request"]["min_protein_g"] == 25


@pytest.mark.parametrize("body", [{"request": "hi"}, {"request": "x" * 1001}])
def test_bad_recipe_requests_are_rejected(client, ready, body):
    assert client.post("/api/v1/recipes/generate", json=body).status_code == 422


def test_no_gemini_key_is_a_clear_503(client, monkeypatch):
    monkeypatch.setattr(routes, "llm_ready", lambda: False)
    response = client.post("/api/v1/recipes/generate", json={"request": "a dinner please"})
    assert response.status_code == 503
    assert "language model" in response.json()["detail"]


def test_a_used_up_quota_is_a_clear_503(client, ready, monkeypatch):
    def out_of_quota(*args, **kwargs):
        raise QuotaExhausted("The daily free-tier limit for this model is used up.")

    monkeypatch.setattr(routes.recipe_service, "generate_recipe", out_of_quota)
    response = client.post("/api/v1/recipes/generate", json={"request": "a light dinner"})
    assert response.status_code == 503
    assert "limit" in response.json()["detail"]


def test_a_slow_gemini_is_a_clear_503_not_a_500(client, ready, monkeypatch):
    from app.core.llm import BUSY_MESSAGE, GeminiUnavailable

    def too_slow(*args, **kwargs):
        raise GeminiUnavailable(BUSY_MESSAGE)

    monkeypatch.setattr(routes.recipe_service, "generate_recipe", too_slow)
    response = client.post("/api/v1/recipes/generate", json={"request": "a light dinner"})
    assert response.status_code == 503
    assert "busy" in response.json()["detail"]


def test_our_errors_never_leak_to_the_caller(client, ready, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("API key AIzaSecret leaked in this message")

    monkeypatch.setattr(routes.planner, "make_plan", explode)
    response = client.post("/api/v1/plans/generate", json={"diet": "vegetarian"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Something went wrong on our side."}


# ---------- the website ----------

def test_the_website_is_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "NutriChef" in page.text
    assert client.get("/app.js").status_code == 200


def test_the_website_does_not_hide_the_api(client):
    """The site is mounted at "/" - mounted too early, it would swallow every route."""
    assert client.get("/health").json()["status"] == "ok"
    assert client.post("/api/v1/auth/login",
                       json={"email": "a@b.com", "password": "x"}).status_code in (401, 422)


def test_warm_up_never_stops_the_app_from_starting(monkeypatch):
    """With no Gemini key or no data yet, warm-up logs a warning and the app still starts."""
    from app.api import main
    from app.services import planner, recipe_service

    def missing(*args, **kwargs):
        raise RuntimeError("GOOGLE_API_KEY is not set in .env")

    monkeypatch.setattr(planner, "load_dependencies", missing)
    monkeypatch.setattr(recipe_service, "load_dependencies", missing)
    monkeypatch.setenv("WARM_UP", "true")
    assert main.create_app() is not None
