# NutriChef AI

**Constraint-aware personalized meal planning & recipe intelligence platform.**

NutriChef turns requests like *"I'm vegetarian, allergic to soy, have paneer and eggs, want a high-protein dinner under 600 kcal"* into recipes and meal plans whose nutrition, allergens, diet rules and budget are checked by deterministic Python — with LLM agents for understanding, generation and critique, RAG over RecipeNLG, and an ML ranker for personalization.

> ⚠️ **Disclaimer:** Nutrition values are estimates. NutriChef is a general wellness and meal-planning tool — not medical advice, diagnosis or treatment, and not a substitute for a doctor or registered dietitian. It **cannot guarantee allergy safety**: always check ingredient labels and cross-contamination risks yourself.

## Status

| Phase | Status |
|---|---|
| 0–1 Analysis & architecture | ✅ |
| 2 Repository & environment setup | ✅ |
| 3 Data acquisition | ✅ |
| 4 Data processing & features | ✅ |
| 5 Nutrition engine | ✅ |
| 6 Allergen, diet & constraint checks | ✅ |
| 7 ML ranking & personalization | ✅ |
| 8 RAG search (ChromaDB) | ✅ |
| 9 LLM agents | ✅ |
| 10 Agent workflow (LangGraph) | ✅ |
| 11–12 Meal planning, inventory & budget | ✅ |
| 13 REST API (FastAPI) | ✅ |
| 14 Database, accounts & saved profiles | ✅ |
| 15+ Streamlit UI, MLOps, deployment | ⏳ |

See [`docs/architecture.md`](docs/architecture.md).

## Tech stack

Python 3.11 · Pandas · scikit-learn · MLflow · LangChain · LangGraph · Gemini · ChromaDB · HuggingFace embeddings · FastAPI · SQLite (SQLAlchemy) · Streamlit · Pytest · Docker · Jenkins · AWS EC2

## Quick start (macOS)

```bash
git clone https://github.com/ShubhranshuVerma/NutriChef_AI.git
cd NutriChef_AI
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                        # then add your GOOGLE_API_KEY
python -m scripts.check                     # settings + data status
python -m scripts.check --ping-llm          # also checks Gemini (1 small request)
pytest
```

## Project layout

```text
app/        backend package (api, agents, core, schemas, services, rag, ml, nutrition, validation, database)
ui/         Streamlit frontend
ml/         training & evaluation scripts, artifacts
data/       reference/ + knowledge_base/ (committed); raw/, processed/, interactions/ (git-ignored)
scripts/    one-off utilities (setup checks, data download, seeding)
tests/      unit, integration, api, agents, rag, ml
docs/       architecture, data sources
```

## Try it

```bash
python -m scripts.demo_recipe        # Scenario 1: one request -> checked recipe (uses your Gemini key)
python -m scripts.demo_meal_plan     # Scenario 2: 7-day plan in a budget + shopping list
python -m scripts.demo_meal_plan --no-llm --days 3 --budget 800
python -m scripts.demo_meal_plan --slots breakfast,lunch,dinner,snack   # fuller days
```

LLM answers are cached on disk (`data/processed/llm_cache`), so repeating a request costs no
Gemini quota and returns instantly — the free tier allows only a few requests per day. After
changing a prompt, clear it:

```bash
python -m scripts.check --clear-llm-cache
```

## API

```bash
uvicorn app.api.main:app --reload     # then open http://127.0.0.1:8000/docs
```

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | what is ready (recipes, model, index, LLM key) |
| POST | `/api/v1/auth/signup`, `/login` | create an account, get a JWT |
| GET/PUT | `/api/v1/users/me/profile` | saved diet, allergies, exclusions, targets |
| GET/PUT | `/api/v1/users/me/inventory` | what you have at home |
| POST | `/api/v1/users/me/feedback` | like/dislike a recipe |
| POST | `/api/v1/recipes/generate` | Scenario 1 — free text → one checked recipe |
| POST | `/api/v1/plans/generate` | Scenario 2 — meal plan in a budget, using your inventory |

Both `generate` endpoints work with or without a token. With one, your saved allergies and
exclusions are **added** to whatever the request asks for — a request can never remove them —
and your saved inventory is used when the request does not send one.

## Data

```bash
python -m scripts.download_usda       # USDA SR Legacy -> data/processed/usda_foods.csv
python -m scripts.sample_recipenlg     # RecipeNLG -> data/processed/recipenlg_sample.csv
python -m scripts.build_ingredient_foods  # catalog ingredients -> USDA nutrients
python -m scripts.process_recipes      # clean recipes -> data/processed/recipes.jsonl
python -m scripts.compute_nutrition    # nutrition + cost -> data/processed/recipes_nutrition.jsonl
python -m scripts.tag_recipes          # allergen/diet tags -> data/processed/recipes_tagged.jsonl
python -m scripts.simulate_users       # simulated users + feedback (training data)
python -m scripts.train_ranker         # train the ranking model -> ml/artifacts/ranker.joblib
python -m scripts.build_index          # search index (ChromaDB) for recipes + knowledge base
python -m scripts.check                # what is ready, what still needs running
```

Datasets and their licenses are listed in [`docs/data_sources.md`](docs/data_sources.md). RecipeNLG is used under its non-commercial research/educational terms and is never committed to this repository.

## Acknowledgements

Some backend patterns were informed by the [mealora-ai-agent](https://github.com/nithinsaikrishnaS/mealora-ai-agent) project (CC BY 4.0 per its README).
