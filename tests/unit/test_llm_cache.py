"""The disk cache that keeps the free Gemini quota from running out."""

from app.core.llm import CachedLLM, FakeLLM, answer_text, clear_cache


def cached(tmp_path, replies, model="test-model"):
    fake = FakeLLM(replies)
    return CachedLLM(fake, model, tmp_path), fake


def test_the_second_identical_prompt_costs_nothing(tmp_path):
    llm, fake = cached(tmp_path, ["the answer"])

    first = answer_text(llm.invoke("what is for dinner?"))
    second = answer_text(llm.invoke("what is for dinner?"))

    assert first == second == "the answer"
    assert len(fake.prompts) == 1          # the model was only called once
    assert (llm.hits, llm.misses) == (1, 1)


def test_a_different_prompt_is_a_different_answer(tmp_path):
    llm, fake = cached(tmp_path, ["dinner answer", "breakfast answer"])

    assert answer_text(llm.invoke("dinner?")) == "dinner answer"
    assert answer_text(llm.invoke("breakfast?")) == "breakfast answer"
    assert len(fake.prompts) == 2


def test_a_different_model_does_not_reuse_the_answer(tmp_path):
    """Otherwise switching model in .env would silently serve the old model's replies."""
    first, _ = cached(tmp_path, ["from model one"], model="one")
    second, fake_two = cached(tmp_path, ["from model two"], model="two")

    assert answer_text(first.invoke("same prompt")) == "from model one"
    assert answer_text(second.invoke("same prompt")) == "from model two"
    assert len(fake_two.prompts) == 1


def test_the_cache_survives_a_restart(tmp_path):
    first, _ = cached(tmp_path, ["remembered"])
    answer_text(first.invoke("a question"))

    second, fake = cached(tmp_path, [])  # no replies left: it must not call the model
    assert answer_text(second.invoke("a question")) == "remembered"
    assert fake.prompts == []


def test_block_style_answers_are_stored_as_plain_text(tmp_path):
    """Gemini returns a list of blocks; the cache should keep the text, not the repr."""
    llm, _ = cached(tmp_path, [[{"type": "text", "text": "hello"}]])
    assert answer_text(llm.invoke("hi")) == "hello"
    assert answer_text(llm.invoke("hi")) == "hello"


def test_clearing_the_cache(tmp_path):
    llm, fake = cached(tmp_path, ["first", "second"])
    answer_text(llm.invoke("a question"))

    assert clear_cache(tmp_path) == 1
    assert answer_text(llm.invoke("a question")) == "second"   # asked again
    assert len(fake.prompts) == 2


def test_clearing_an_empty_cache_is_fine(tmp_path):
    assert clear_cache(tmp_path / "never-created") == 0


def test_other_attributes_reach_the_real_model(tmp_path):
    llm, fake = cached(tmp_path, [])
    assert llm.prompts is fake.prompts
