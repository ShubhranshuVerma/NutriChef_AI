# NutriChef AI: one image that runs the API and the website.
#
#   docker compose up --build        (see compose.yml)
#
# The image holds the code and the small reference files only. Everything
# built from licensed or large data (the recipe library, the search index,
# the database, saved Gemini answers, the trained ranker) stays on your disk
# and is mounted in, so it is never baked into an image.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# PyTorch for CPU only. The default download also bundles GPU libraries
# (about 2 GB more) that a server without a GPU never uses.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

# Libraries next, before the code: this slow step is then reused from
# Docker's cache every time only the code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# The search model (about 90 MB, Apache-2.0) goes into the image now, so the app
# never has to download it or check Hugging Face for updates when it starts.
# Keep this name the same as EMBEDDING_MODEL in .env.
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
ENV HF_HUB_OFFLINE=1

# Run as a normal user, not as root.
RUN useradd --create-home --uid 1000 chef

COPY app ./app
COPY web ./web
COPY scripts ./scripts
COPY data/reference ./data/reference
COPY data/knowledge_base ./data/knowledge_base
RUN mkdir -p data/processed ml/artifacts && chown -R chef:chef /app

USER chef

EXPOSE 8000

# Docker marks the container unhealthy if /health stops answering.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
