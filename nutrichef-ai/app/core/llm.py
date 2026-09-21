"""One place to create the LLM, and a fake one for tests.

Agents take an `llm` object with an `.invoke(prompt)` method that returns
something with `.content`. That keeps tests offline and free.
"""

from app.core.config import get_settings


def get_llm(temperature=None):
    """Gemini, configured from .env."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    settings = get_settings()
    if not settings.has_llm_key:
        raise RuntimeError("GOOGLE_API_KEY is not set in .env")
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key.get_secret_value(),
        temperature=settings.llm_temperature if temperature is None else temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


class FakeReply:
    def __init__(self, content):
        self.content = content


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
