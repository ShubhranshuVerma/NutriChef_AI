"""One place to create the LLM, and a fake one for tests.

Agents take an `llm` object with an `.invoke(prompt)` method that returns
something with `.content`. That keeps tests offline and free.

Answers are cached on disk by default: the same prompt to the same model costs
nothing and returns instantly. The free Gemini tier allows very few requests a
day, and clicking around a UI would otherwise exhaust it in minutes.
"""

import hashlib
import time

from app.core.config import PROJECT_ROOT, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "llm_cache"

# Gemini's free tier fails in two very different ways.
BUSY = ("503", "UNAVAILABLE", "overloaded", "high demand", "INTERNAL", "deadline")
OUT_OF_QUOTA = ("429", "RESOURCE_EXHAUSTED", "exceeded your current quota")


class QuotaExhausted(RuntimeError):
    """The daily free-tier allowance is gone. Waiting a few seconds will not help."""


def invoke_with_retry(llm, prompt, attempts=3, wait_seconds=15):
    """Call the model, waiting and retrying when the server is merely busy.

    A 503 ("high demand") is temporary and worth retrying. A 429 is the daily
    quota and is not, so we stop immediately and say so in one clear line.
    """
    for attempt in range(1, attempts + 1):
        try:
            return llm.invoke(prompt)
        except Exception as error:
            message = str(error)
            if any(word in message for word in OUT_OF_QUOTA):
                raise QuotaExhausted(
                    "The daily Gemini quota for this project and model is used up. "
                    "Wait for it to reset, or set a different GEMINI_MODEL in .env."
                ) from error
            if attempt == attempts or not any(word in message for word in BUSY):
                raise
            pause = wait_seconds * attempt
            log.warning("Gemini is busy (attempt %d of %d); waiting %ds", attempt, attempts, pause)
            time.sleep(pause)
    raise RuntimeError("unreachable")


def answer_text(answer):
    """Get plain text out of an LLM answer.

    Newer LangChain models return `.content` as a list of blocks such as
    [{"type": "text", "text": "..."}] instead of a plain string.
    """
    content = getattr(answer, "content", answer)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content)


class FakeReply:
    def __init__(self, content):
        self.content = content


class CachedLLM:
    """Remembers each answer on disk, keyed by the prompt and the model name.

    A cached answer is the OLD answer: after changing a prompt, clear the cache
    (delete data/processed/llm_cache) or you will keep reading the old replies.
    """

    def __init__(self, llm, model, directory=CACHE_DIR):
        self.llm = llm
        self.model = model
        self.directory = directory
        self.hits = 0
        self.misses = 0

    def path_for(self, prompt):
        key = hashlib.sha256(f"{self.model}\n{prompt}".encode()).hexdigest()[:32]
        return self.directory / f"{key}.txt"

    def invoke(self, prompt):
        path = self.path_for(str(prompt))
        if path.exists():
            self.hits += 1
            log.info("llm cache hit (%s)", path.name)
            return FakeReply(path.read_text(encoding="utf-8"))

        answer = self.llm.invoke(prompt)  # retries happen one level up, in agents.ask
        text = answer_text(answer)
        self.misses += 1
        self.directory.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return FakeReply(text)

    def __getattr__(self, name):
        return getattr(self.llm, name)  # anything else goes to the real model


def get_llm(temperature=None, cache=None):
    """Gemini, configured from .env, wrapped in the disk cache unless turned off."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    settings = get_settings()
    if not settings.has_llm_key:
        raise RuntimeError("GOOGLE_API_KEY is not set in .env")
    llm = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key.get_secret_value(),
        temperature=settings.llm_temperature if temperature is None else temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    use_cache = settings.llm_cache if cache is None else cache
    return CachedLLM(llm, settings.gemini_model) if use_cache else llm


def clear_cache(directory=CACHE_DIR):
    """Delete every cached answer. Returns how many files were removed."""
    if not directory.exists():
        return 0
    files = list(directory.glob("*.txt"))
    for path in files:
        path.unlink()
    return len(files)


class FakeLLM:
    """Returns prepared answers in order. Used by the tests."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if not self.replies:
            raise AssertionError("FakeLLM ran out of replies")
        return FakeReply(self.replies.pop(0))
