"""The API and the website it serves. The services are replaced with fakes."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import limits, routes
from app.api.main import create_app
from app.core.config import get_settings
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


# ---------- the hourly limit on recipe requests ----------

def ask_for_recipes(client, monkeypatch, times, headers=None):
    monkeypatch.setattr(routes.recipe_service, "generate_recipe",
                        lambda request_text, profile=None, deps=None: FAKE_RECIPE)
    return [client.post("/api/v1/recipes/generate", headers=headers or {},
                        json={"request": "paneer dinner"}).status_code for _ in range(times)]


def test_too_many_recipe_requests_get_a_clear_429(client, ready, monkeypatch):
    monkeypatch.setenv("RECIPE_REQUESTS_PER_HOUR", "3")
    get_settings.cache_clear()
    assert ask_for_recipes(client, monkeypatch, 4) == [200, 200, 200, 429]

    response = client.post("/api/v1/recipes/generate", json={"request": "paneer dinner"})
    assert "3 recipes in the last hour" in response.json()["detail"]
    assert int(response.headers["Retry-After"]) > 0


def test_the_limit_resets_after_an_hour(client, ready, monkeypatch):
    monkeypatch.setenv("RECIPE_REQUESTS_PER_HOUR", "1")
    get_settings.cache_clear()
    clock = [1_000_000.0]
    monkeypatch.setattr(limits.time, "time", lambda: clock[0])
    assert ask_for_recipes(client, monkeypatch, 2) == [200, 429]
    clock[0] += limits.WINDOW_SECONDS + 1
    assert ask_for_recipes(client, monkeypatch, 1) == [200]


def test_each_person_has_their_own_limit(ready, monkeypatch):
    monkeypatch.setenv("RECIPE_REQUESTS_PER_HOUR", "1")
    get_settings.cache_clear()
    class Someone:
        def __init__(self, id):
            self.id = id
    class Request:
        client = None
    limits.check_recipe_limit(Request(), Someone(1))
    limits.check_recipe_limit(Request(), Someone(2))       # a different account: fine
    with pytest.raises(HTTPException):
        limits.check_recipe_limit(Request(), Someone(1))


def test_zero_means_no_limit(client, ready, monkeypatch):
    monkeypatch.setenv("RECIPE_REQUESTS_PER_HOUR", "0")
    get_settings.cache_clear()
    assert set(ask_for_recipes(client, monkeypatch, 25)) == {200}


def test_meal_plans_are_not_limited(client, ready, monkeypatch):
    """Plans never call Gemini, so they cost nothing to repeat."""
    monkeypatch.setenv("RECIPE_REQUESTS_PER_HOUR", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(routes.planner, "make_plan", lambda *a, **k: FAKE_PLAN)
    codes = {client.post("/api/v1/plans/generate", json={"days": 1}).status_code for _ in range(3)}
    assert codes == {200}
