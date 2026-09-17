"""Simple logging setup using Python's built-in `logging` module.

Usage:
    from app.core.logging import configure_logging, get_logger
    configure_logging()                 # once, at program start
    log = get_logger(__name__)
    log.info("recipe generated in %d iterations", 2)
"""

import logging
import re
import sys

from app.core.config import get_settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# Google API keys start with "AIza"; also mask "Bearer <token>" values.
_SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
]


class RedactSecretsFilter(logging.Filter):
    """Safety net: mask anything that looks like a secret before it is printed."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(
                lambda m: (m.group(1) if m.groups() else "") + "***REDACTED***", redacted
            )
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


def configure_logging(level: str | None = None) -> None:
    """Configure the root logger. Safe to call more than once."""
    level = (level or get_settings().log_level).upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(RedactSecretsFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Hide INFO chatter from third-party libraries.
    for noisy in ("httpx", "httpcore", "urllib3", "chromadb", "sentence_transformers", "mlflow"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
