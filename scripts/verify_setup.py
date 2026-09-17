"""Check that the local NutriChef environment is ready.

Run from the project root:
    python -m scripts.verify_setup              # offline checks
    python -m scripts.verify_setup --ping-llm   # also sends one tiny request to Gemini
"""

import argparse
import importlib
import os
import sys
from importlib.metadata import PackageNotFoundError, version

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")  # silence MLflow's import banner

from app.core.config import PROJECT_ROOT, get_settings
from app.core.logging import configure_logging, get_logger

# (import name, distribution name)
REQUIRED_PACKAGES = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("pydantic", "pydantic"),
    ("pydantic_settings", "pydantic-settings"),
    ("sqlalchemy", "sqlalchemy"),
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("sklearn", "scikit-learn"),
    ("mlflow", "mlflow"),
    ("langchain", "langchain"),
    ("langchain_google_genai", "langchain-google-genai"),
    ("langgraph", "langgraph"),
    ("langchain_chroma", "langchain-chroma"),
    ("chromadb", "chromadb"),
    ("sentence_transformers", "sentence-transformers"),
    ("streamlit", "streamlit"),
    ("bcrypt", "bcrypt"),
    ("jwt", "pyjwt"),
]

REQUIRED_DIRS = [
    "app/core",
    "data/raw",
    "data/processed",
    "data/knowledge_base",
    "data/reference",
    "ml/artifacts",
    "tests/unit",
]

OK, FAIL, WARN = "[ OK ]", "[FAIL]", "[WARN]"


def check_python() -> bool:
    major, minor = sys.version_info[:2]
    good = (major, minor) == (3, 11)
    print(f"{OK if good else FAIL} Python {sys.version.split()[0]} (expected 3.11.x)")
    return good


def check_packages() -> bool:
    all_good = True
    for module_name, dist_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(module_name)
            print(f"{OK} {dist_name:<24} {version(dist_name)}")
        except (ImportError, PackageNotFoundError) as exc:
            all_good = False
            print(f"{FAIL} {dist_name:<24} not importable: {exc}")
    return all_good


def check_accelerator() -> None:
    try:
        import torch

        if torch.backends.mps.is_available():
            print(f"{OK} PyTorch {torch.__version__} - Apple GPU (MPS) available")
        else:
            print(f"{WARN} PyTorch {torch.__version__} - CPU only (fine for this project)")
    except ImportError:
        print(f"{WARN} PyTorch not installed")


def check_dirs() -> bool:
    missing = [d for d in REQUIRED_DIRS if not (PROJECT_ROOT / d).is_dir()]
    if missing:
        print(f"{FAIL} Missing folders: {', '.join(missing)}")
        return False
    print(f"{OK} Project folders present")
    return True


def check_settings() -> bool:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        print(f"{OK} .env found")
    else:
        print(f"{WARN} .env not found - run: cp .env.example .env")

    try:
        settings = get_settings()
    except Exception as exc:
        print(f"{FAIL} Settings invalid: {exc}")
        return False

    print(f"{OK} Settings loaded (env={settings.environment}, model={settings.gemini_model})")
    if settings.has_llm_key:
        key = settings.google_api_key.get_secret_value()
        print(f"{OK} GOOGLE_API_KEY set ({key[:4]}...{key[-2:]}, {len(key)} chars)")
    else:
        print(f"{WARN} GOOGLE_API_KEY is empty - LLM features will not work yet")
    if settings.jwt_secret_key.get_secret_value() == "change-me":
        print(f"{WARN} JWT_SECRET_KEY is the placeholder - fine for now, change before deploying")
    return True


def ping_llm() -> bool:
    settings = get_settings()
    if not settings.has_llm_key:
        print(f"{FAIL} Cannot ping Gemini: GOOGLE_API_KEY is empty")
        return False

    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key.get_secret_value(),
        temperature=0,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )
    try:
        reply = llm.invoke("Reply with exactly one word: OK")
    except Exception as exc:
        print(f"{FAIL} Gemini call failed: {type(exc).__name__}: {str(exc)[:200]}")
        return False

    text = reply.text if hasattr(reply, "text") else str(reply.content)
    text = text() if callable(text) else text  # older langchain-core exposes .text()
    usage = getattr(reply, "usage_metadata", None) or {}
    tokens = usage.get("total_tokens", "n/a")
    print(f"{OK} Gemini ({settings.gemini_model}) replied: {text.strip()!r} (tokens={tokens})")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ping-llm", action="store_true", help="send one small request to Gemini")
    args = parser.parse_args()

    configure_logging()
    get_logger(__name__).info("Verifying NutriChef setup in %s", PROJECT_ROOT)

    results = [check_python(), check_packages(), check_dirs(), check_settings()]
    check_accelerator()
    if args.ping_llm:
        results.append(ping_llm())

    if all(results):
        print("\nSetup looks good.")
        return 0
    print("\nSetup has problems - see [FAIL] lines above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
