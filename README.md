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
| 15 Web app (HTML/CSS/JS on FastAPI) | ✅ |
| 16 Test suite & coverage | ✅ |
| 17 Observability (LangSmith tracing) | ✅ |
| 18+ Docker, Jenkins, AWS | ⏳ |

See [`docs/architecture.md`](docs/architecture.md).

## Tech stack

Python 3.11 · Pandas · scikit-learn · MLflow · LangChain · LangGraph · LangSmith · Gemini · ChromaDB · HuggingFace embeddings · FastAPI · SQLite (SQLAlchemy) · Pytest · Docker · Jenkins · AWS EC2

## Quick start (macOS)

```bash
git clone https://github.com/ShubhranshuVerma/NutriChef_AI.git
cd NutriChef_AI
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                        # add GOOGLE_API_KEY, and LANGSMITH_API_KEY for traces
python -m scripts.check                     # settings + data status
python -m scripts.check --ping-llm          # also checks Gemini (1 small request)
pytest
pytest --cov=app --cov-report=term-missing  # coverage, and which lines are missing
```

About 90 tests, one file per part of the project, in `tests/`. Gemini is replaced with a fake
that returns scripted replies, so the suite is free, offline and takes a few seconds. Three
nutrition tests check against your real USDA table and are skipped until it is built.

## Project layout

```text
app/        backend package (api, agents, core, schemas, services, rag, ml, nutrition, validation, database)
web/        the website (index.html, styles.css, app.js)
ml/         artifacts/ - the trained ranking model (git-ignored)
data/       reference/ + knowledge_base/ (committed); raw/, processed/, interactions/ (git-ignored)
scripts/    build_data, train_ranker, demo, check
tests/      one file per part: checks, nutrition, data, planner, agents, api, auth, ml
docs/       architecture, data sources
```

## Try it

```bash
python -m scripts.demo recipe        # Scenario 1: one request -> checked recipe (uses your Gemini key)
python -m scripts.demo plan          # Scenario 2: 7-day plan in a budget + shopping list (no Gemini key needed)
python -m scripts.demo plan --days 3 --budget 800
python -m scripts.demo plan --slots breakfast,lunch,dinner,snack   # fuller days
```

LLM answers are cached on disk (`data/processed/llm_cache`), so repeating a request gives the
same result, costs no Gemini quota and returns instantly — the free tier allows only a few requests per day. After
changing a prompt, clear it:

```bash
python -m scripts.check --clear-llm-cache
```

How long Gemini takes depends mostly on how hard it thinks before answering. `LLM_THINKING=low`
in `.env` is the default here (the model's own default is `medium`). To see the difference on
your key — each run uses 1-3 requests of the daily quota:

```bash
python -m scripts.demo recipe --no-cache --thinking medium
python -m scripts.demo recipe --no-cache --thinking low
```

## Watching it think (LangSmith)

Put a LangSmith key in `.env` and every run is traced — each agent, each prompt and reply,
and the deterministic steps too:

```bash
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=nutrichef-ai
```

Then open [smith.langchain.com](https://smith.langchain.com) and pick the project. A recipe
request reads **understand → search → write → check → finish**, with **critique → revise** in
between only when Python found something to fix, and the time each step took. The `check` step
is where Python calculates the nutrition and decides whether the recipe is safe - you can open
it and see the numbers and the verdict. LangChain and LangGraph report all of this themselves;
nothing in the code has to mention tracing beyond switching it on.

No key means no tracing, no network calls and no change in behaviour. `python -m scripts.check`
says which it is.

## Run it

```bash
uvicorn app.api.main:app --reload
```

| | |
|---|---|
| http://127.0.0.1:8000 | **the website** |
| http://127.0.0.1:8000/docs | the API reference |

The site in `web/` is plain HTML, CSS and JavaScript — no build step, no framework — served by
FastAPI itself, so one command runs the whole product. The food photography is loaded from
[Pexels](https://www.pexels.com/license/) under their free licence, so nothing is committed to
this repository; with no internet each photo frame falls back to a warm gradient and the page
still works.

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
python -m scripts.build_data           # every step: usda, recipenlg, foods, recipes, nutrition, tags, index
python -m scripts.build_data tags      # or just the steps you name
python -m scripts.train_ranker         # simulated users + train the ranking model (logged to MLflow)
python -m scripts.check                # what is ready, what still needs running
```

Datasets and their licenses are listed in [`docs/data_sources.md`](docs/data_sources.md). RecipeNLG is used under its non-commercial research/educational terms and is never committed to this repository.

## Acknowledgements

Some backend patterns were informed by the [mealora-ai-agent](https://github.com/nithinsaikrishnaS/mealora-ai-agent) project (CC BY 4.0 per its README).
