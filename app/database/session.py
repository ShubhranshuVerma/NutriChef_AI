"""One engine, one session maker, and `create_all` at startup.

No migration tool: the schema is small and SQLite is a file. If it changes during
development, delete data/processed/nutrichef.db and let it be recreated.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import PROJECT_ROOT, get_settings
from app.database.models import Base

_engine = None
_Session = None


def database_url():
    """Make a relative sqlite path absolute, so it works from any folder."""
    url = get_settings().database_url
    prefix = "sqlite:///"
    if url.startswith(prefix) and not url.startswith(prefix + "/"):
        path = PROJECT_ROOT / url[len(prefix):]
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"{prefix}{path}"
    return url


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(database_url(), connect_args={"check_same_thread": False})
    return _engine


def create_tables():
    Base.metadata.create_all(engine())


def get_session():
    """FastAPI dependency: one session per request, always closed."""
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=engine(), autoflush=False, expire_on_commit=False)
    session = _Session()
    try:
        yield session
    finally:
        session.close()


def reset(url=None):
    """Point at a different database (used by the tests)."""
    global _engine, _Session
    _engine = create_engine(url, connect_args={"check_same_thread": False}) if url else None
    _Session = None
    if url:
        Base.metadata.create_all(_engine)
