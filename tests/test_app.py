"""Unit tests for app.py logging and redaction."""

import logging
from app import RedactionFilter


def test_redaction_filter_gemini_key():
    """Verify Gemini API keys are redacted from logs."""
    filter_ = RedactionFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Connecting using key AIzaSyA1234567890abcdefghijklmnopqrstuv to API",
        args=(),
        exc_info=None,
    )
    filter_.filter(record)
    assert "AIzaSyA1234567890abcdefghijklmnopqrstuv" not in record.msg
    assert "[REDACTED_API_KEY]" in record.msg


def test_redaction_filter_generic_token():
    """Verify generic auth tokens and passwords are redacted."""
    filter_ = RedactionFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Got response with token: my_secret_token_value_12345",
        args=(),
        exc_info=None,
    )
    filter_.filter(record)
    assert "my_secret_token_value_12345" not in record.msg
    assert "[REDACTED]" in record.msg
