"""Unit tests for app.py logging and redaction."""

import logging
from app import RedactionFilter


def test_redaction_filter_api_key():
    """Verify API keys are redacted from logs."""
    filter_ = RedactionFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Connecting using key: fake-test-key-not-real to API",
        args=(),
        exc_info=None,
    )
    filter_.filter(record)
    assert "fake-test-key-not-real" not in record.msg
    assert "[REDACTED]" in record.msg


def test_redaction_filter_generic_token():
    """Verify generic auth tokens and passwords are redacted."""
    filter_ = RedactionFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Got response with token: fake-test-token-not-real",
        args=(),
        exc_info=None,
    )
    filter_.filter(record)
    assert "fake-test-token-not-real" not in record.msg
    assert "[REDACTED]" in record.msg
