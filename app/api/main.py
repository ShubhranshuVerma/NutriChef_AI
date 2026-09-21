"""The FastAPI application.

Run it:
    uvicorn app.api.main:app --reload
    open http://127.0.0.1:8000        the website
    open http://127.0.0.1:8000/docs   the API reference
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, users
from app.api.routes import VERSION, health_router, router
from app.core.config import PROJECT_ROOT, get_settings
from app.core.llm import GeminiUnavailable, QuotaExhausted
from app.core.logging import configure_logging, get_logger
from app.core.tracing import configure_tracing
from app.database.session import create_tables

log = get_logger(__name__)

DESCRIPTION = """
NutriChef AI turns a food request into recipes and meal plans whose nutrition,
allergens, diet rules and budget are checked by deterministic Python.

Nutrition values and prices are estimates. This is a general wellness tool, not
medical advice, and it cannot guarantee allergy safety.
"""


def warm_up():
    """Load everything the two scenarios need now, not on the first visitor's request."""
    from app.services import planner, recipe_service

    for name, load in [("meal plans", planner.load_dependencies),
                       ("recipes", recipe_service.load_dependencies)]:
        try:
            load()
            log.info("warm-up: %s ready", name)
        except Exception as error:   # e.g. no Gemini key or no data yet: the app still starts
            log.warning("warm-up: %s not loaded yet (%s)", name, error)


def create_app():
    configure_logging()
    configure_tracing()          # before anything builds an LLM
    create_tables()
    if get_settings().warm_up:
        warm_up()
    app = FastAPI(title=get_settings().app_name, description=DESCRIPTION, version=VERSION)
    app.include_router(health_router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(router)

    @app.exception_handler(QuotaExhausted)
    async def out_of_quota(request: Request, error: QuotaExhausted):
        """A quota problem is ours to explain, not a mystery 500."""
        log.warning("gemini quota exhausted on %s", request.url.path)
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.exception_handler(GeminiUnavailable)
    async def gemini_busy(request: Request, error: GeminiUnavailable):
        """Gemini too slow or overloaded: a clear 503, not a mystery 500."""
        log.warning("gemini unavailable on %s: %s", request.url.path, error.__cause__)
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        """Log the real error, tell the caller nothing about our internals."""
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500,
                            content={"detail": "Something went wrong on our side."})

    # The website. Mounted last so every /api and /health route wins the match.
    website = PROJECT_ROOT / "web"
    if website.is_dir():
        app.mount("/", StaticFiles(directory=website, html=True), name="web")

    return app


app = create_app()
