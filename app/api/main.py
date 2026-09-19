"""The FastAPI application.

Run it:
    uvicorn app.api.main:app --reload
    open http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import auth, users
from app.api.routes import VERSION, health_router, router
from app.core.config import get_settings
from app.core.llm import QuotaExhausted
from app.core.logging import configure_logging, get_logger
from app.database.session import create_tables

log = get_logger(__name__)

DESCRIPTION = """
NutriChef AI turns a food request into recipes and meal plans whose nutrition,
allergens, diet rules and budget are checked by deterministic Python.

Nutrition values and prices are estimates. This is a general wellness tool, not
medical advice, and it cannot guarantee allergy safety.
"""


def create_app():
    configure_logging()
    create_tables()
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

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        """Log the real error, tell the caller nothing about our internals."""
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500,
                            content={"detail": "Something went wrong on our side."})

    return app


app = create_app()
