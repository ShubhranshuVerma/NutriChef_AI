import logging

from app.core.logging import configure_logging, get_logger


def test_messages_are_printed(capsys):
    configure_logging(level="INFO")
    get_logger("nutrichef.test").info("hello %s", "world")
    out = capsys.readouterr().out
    assert "INFO" in out and "hello world" in out


def test_secrets_are_redacted(capsys):
    configure_logging(level="INFO")
    log = get_logger("nutrichef.test")
    log.info("key=%s", "AIzaSyFAKE_FAKE_FAKE_FAKE_FAKE_123")
    log.info("Authorization: Bearer abc.def.ghi")
    out = capsys.readouterr().out
    assert "AIzaSyFAKE" not in out
    assert "abc.def.ghi" not in out
    assert out.count("***REDACTED***") == 2


def test_level_filtering(capsys):
    configure_logging(level="WARNING")
    log = get_logger("nutrichef.test")
    log.info("hidden")
    log.warning("shown")
    out = capsys.readouterr().out
    assert "hidden" not in out and "shown" in out


def test_configure_is_idempotent():
    configure_logging()
    configure_logging()
    assert len(logging.getLogger().handlers) == 1
