"""LangSmith tracing, switched on by the key in `.env`.

LangSmith reads its settings from the environment, not from our Settings, so
this copies them across once at start-up. After that LangChain and LangGraph
report every model call and every graph step on their own - nothing else in
the project has to mention tracing.

No LANGSMITH_API_KEY in `.env` means tracing stays off and nothing is sent.
"""

import os

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


def configure_tracing():
    """Copy the LangSmith settings into the environment. Returns True if it is on."""
    settings = get_settings()
    if settings.langsmith_api_key is None:
        os.environ["LANGSMITH_TRACING"] = "false"
        log.info("LangSmith tracing is off (no LANGSMITH_API_KEY in .env)")
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.get_secret_value()
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint

    # LangSmith remembers the environment the first time it looks. Make it look again,
    # or a change to .env can be silently ignored for the life of the process.
    from langsmith import utils
    utils.get_env_var.cache_clear()

    log.info("LangSmith tracing is on (project %r)", settings.langsmith_project)
    return True
