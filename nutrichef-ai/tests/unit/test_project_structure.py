"""Guards against accidentally committing secrets or losing the layout."""

from app.core.config import PROJECT_ROOT

EXPECTED_PACKAGES = [
    "app/api",
    "app/agents",
    "app/core",
    "app/schemas",
    "app/services",
    "app/rag",
    "app/ml",
    "app/nutrition",
    "app/validation",
    "app/database",
]


def test_expected_packages_exist():
    for pkg in EXPECTED_PACKAGES:
        assert (PROJECT_ROOT / pkg / "__init__.py").is_file(), pkg


def test_gitignore_blocks_secrets_and_data():
    rules = (PROJECT_ROOT / ".gitignore").read_text()
    for rule in (".env", "*.db", "mlruns/", "**/RecipeNLG*", ".venv/"):
        assert rule in rules, rule


def test_env_example_has_no_real_key():
    for line in (PROJECT_ROOT / ".env.example").read_text().splitlines():
        if line.startswith("GOOGLE_API_KEY="):
            assert line.strip() == "GOOGLE_API_KEY="
