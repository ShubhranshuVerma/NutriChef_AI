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
| 18 Docker | ✅ |
| 19 Jenkins | ✅ |
| 20 AWS EC2 | ✅ |

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

About 110 tests, one file per part of the project, in `tests/`. Gemini is replaced with a fake
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

## Run it in Docker

Needs [Docker Desktop](https://www.docker.com/products/docker-desktop/). Build the data first
(see **Data** below), because the image holds only the code: your recipe library, search index,
database, saved Gemini answers and trained ranker stay on your disk and are mounted in.

```bash
docker compose up --build        # first build takes a few minutes (PyTorch)
```

Open http://127.0.0.1:8000. Stop it with Ctrl+C, or run it in the background:

```bash
docker compose up -d
docker compose logs -f
docker compose down
```

| File | What it does |
|---|---|
| `Dockerfile` | Python 3.11, CPU-only PyTorch (about 2 GB smaller), the requirements, the search model (so it never downloads at start), then the code; runs as a normal user, with a health check on `/health` |
| `compose.yml` | reads your keys from `.env`, mounts `data/processed` and `ml/artifacts`, and turns on warm-up: the library and search model load when the container starts, not on the first request |
| `.dockerignore` | keeps `.env`, raw data and local clutter out of the image |

`.env` is never copied into the image. The ranker must be trained with the same scikit-learn
version the image installs (the one in `requirements.txt`); if it cannot be read, plans still
work on the rule score and the log says to run `python -m scripts.train_ranker`.

## Jenkins: every push is tested and built

[`Jenkinsfile`](Jenkinsfile) checks each change pushed to GitHub. Jenkins takes a clean copy
of the code (not your working folder) and runs:

| Stage | What it does |
|---|---|
| Setup | makes a `.venv` and installs `requirements.txt` and `requirements-dev.txt` |
| Test | `pytest`; an HTML report **opens in your browser** when the stage ends (pass or fail), is kept with the build under **Build Artifacts**, and the results also appear on the build's **Tests** page with a trend graph |
| Build image | `docker build -t nutrichef-ai:<build number> -t nutrichef-ai:latest .` |
| Smoke test | starts that image and checks `/health` answers (asked from inside the container, so no port can clash) |

Jenkins looks at GitHub every 5 minutes and builds new commits; **Build Now** runs it any time.
If a stage fails, the rest are skipped and that stage's log shows why. The tests need no
`.env` and no data, and no Gemini request is made.

Rebuilding the data and the ranker is not part of it; run those yourself when needed:
`python -m scripts.build_data --rebuild`, then `python -m scripts.train_ranker`.

**One-time setup** (Homebrew; Docker Desktop running):

```bash
brew install jenkins-lts
brew services start jenkins-lts
cat ~/.jenkins/secrets/initialAdminPassword
```

1. Open http://localhost:8080, paste the password, choose **Install suggested plugins**, and
   create your user.
2. **New Item** → name `nutrichef` → **Pipeline** → OK.
3. Under **Pipeline**: Definition **Pipeline script from SCM** → SCM **Git** → Repository URL
   `https://github.com/ShubhranshuVerma/NutriChef_AI.git` → Branch `*/main` →
   Script Path `Jenkinsfile` → **Save**.
4. Click **Build Now**. The first build takes a while (libraries and the image); later ones reuse
   them.

The `Jenkinsfile` expects Python 3.11 at `~/.pyenv/versions/3.11.8/bin/python3` (the `PYTHON`
line at its top; `pyenv which python` shows yours). Stop Jenkins with
`brew services stop jenkins-lts`.

## Deploy on AWS EC2

One small Ubuntu server runs the same `docker compose` as your Mac.

**1. Launch the server** (EC2 → Launch instance)

- Name `nutrichef`, image **Ubuntu Server 24.04 LTS (x86)**, type **t3.small**
- Key pair: create `nutrichef-key` (.pem) and keep it in `~/.ssh`
- Security group: **SSH (22) from My IP**, **HTTP (80) from Anywhere**
- Storage: **20 GiB**

**2. From your Mac: log in and copy what git does not hold**

```bash
chmod 400 ~/.ssh/nutrichef-key.pem
ssh -i ~/.ssh/nutrichef-key.pem ubuntu@<public-ip>
```

**3. On the server: install Docker and get the code**

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker ubuntu
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
git clone https://github.com/ShubhranshuVerma/NutriChef_AI.git
exit
```

**4. From your Mac: copy the data, the model and the settings**

```bash
cd ~/NutriChef_AI
scp -i ~/.ssh/nutrichef-key.pem -r data/processed ubuntu@<public-ip>:~/NutriChef_AI/data/
scp -i ~/.ssh/nutrichef-key.pem -r ml/artifacts ubuntu@<public-ip>:~/NutriChef_AI/ml/
scp -i ~/.ssh/nutrichef-key.pem .env ubuntu@<public-ip>:~/NutriChef_AI/.env
```

**5. On the server: settings for production, then start**

Log in first (`ssh` on its own line), then paste the rest after the `ubuntu@...$` prompt:

```bash
ssh -i ~/.ssh/nutrichef-key.pem ubuntu@<public-ip>
```

```bash
cd ~/NutriChef_AI
chmod 600 .env
sed -i '/^ENVIRONMENT=/d;/^PUBLISH_PORT=/d;/^JWT_SECRET_KEY=/d' .env
echo "ENVIRONMENT=production" >> .env
echo "PUBLISH_PORT=80" >> .env
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" >> .env
docker compose up -d --build
docker compose ps
```

This switches the copied `.env` to production, opens port 80 and gives the server its own login
secret. Production refuses to start with a weak secret or no Gemini key. Wait for `(healthy)`.

Open `http://<public-ip>`. To update later: `git pull` then `docker compose up -d --build`.
Stop the instance in the EC2 console when you are not using it (it costs money while running);
**Terminate** it to delete it and its disk for good.

The site is plain HTTP, so passwords travel unencrypted: fine for a demo, not for real users.

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
