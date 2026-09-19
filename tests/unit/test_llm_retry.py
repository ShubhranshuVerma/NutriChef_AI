"""Retrying a busy model, and giving up honestly when the quota is gone."""

import pytest

from app.core.llm import QuotaExhausted, invoke_with_retry


class Flaky:
    """Raises the given errors in order, then answers."""

    def __init__(self, errors, answer="the answer"):
        self.errors = list(errors)
        self.answer = answer
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        if self.errors:
            raise RuntimeError(self.errors.pop(0))
        return self.answer


BUSY = "503 UNAVAILABLE. This model is currently experiencing high demand."
QUOTA = ("429 RESOURCE_EXHAUSTED. You exceeded your current quota, "
         "limit: 20, model: gemini-3.5-flash")


def test_a_busy_model_is_retried(caplog):
    llm = Flaky([BUSY, BUSY])
    assert invoke_with_retry(llm, "a prompt", wait_seconds=0) == "the answer"
    assert llm.calls == 3


def test_it_gives_up_after_the_last_attempt():
    llm = Flaky([BUSY, BUSY, BUSY])
    with pytest.raises(RuntimeError, match="503"):
        invoke_with_retry(llm, "a prompt", attempts=3, wait_seconds=0)
    assert llm.calls == 3


def test_running_out_of_quota_is_not_retried():
    """Waiting 15 seconds cannot give back a daily allowance."""
    llm = Flaky([QUOTA])
    with pytest.raises(QuotaExhausted, match="daily Gemini quota"):
        invoke_with_retry(llm, "a prompt", wait_seconds=0)
    assert llm.calls == 1


def test_the_quota_message_is_ours_not_googles():
    llm = Flaky([QUOTA])
    with pytest.raises(QuotaExhausted) as error:
        invoke_with_retry(llm, "a prompt", wait_seconds=0)
    assert "GEMINI_MODEL" in str(error.value)      # tells the person what to do
    assert "quotaMetric" not in str(error.value)   # not a wall of Google JSON


def test_other_errors_fail_immediately():
    """A bad API key should not be retried three times over 45 seconds."""
    llm = Flaky(["400 API key not valid"])
    with pytest.raises(RuntimeError, match="API key"):
        invoke_with_retry(llm, "a prompt", wait_seconds=0)
    assert llm.calls == 1


def test_a_working_model_is_called_once():
    llm = Flaky([])
    assert invoke_with_retry(llm, "a prompt", wait_seconds=0) == "the answer"
    assert llm.calls == 1
