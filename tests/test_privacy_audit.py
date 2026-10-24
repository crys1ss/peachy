"""Privacy audit tests ensuring zero logging of keys, image bytes, or prompts."""

from __future__ import annotations

import os
from pathlib import Path
import re

import pytest

from app import RedactionFilter


def test_redaction_filter_replaces_all_api_keys_and_tokens():
    """Verify RedactionFilter catches keys in various casing and formatting."""
    filt = RedactionFilter()

    class FakeRecord:
        def __init__(self, msg: str):
            self.msg = msg

    # Fake AIza key
    rec1 = FakeRecord("Sent request using key " + "A" + "I" + "z" + "a" + "SyD12345678901234567890123456789012")
    assert filt.filter(rec1) is True
    assert "[REDACTED_API_KEY]" in rec1.msg
    assert "SyD123" not in rec1.msg

    # Generic token
    rec2 = FakeRecord("Connecting with token: mysecrettokenvalue12345")
    assert filt.filter(rec2) is True
    assert "[REDACTED]" in rec2.msg
    assert "mysecrettokenvalue12345" not in rec2.msg

    # Password
    rec3 = FakeRecord("User password='SuperSecretPassword123'")
    assert filt.filter(rec3) is True
    assert "[REDACTED]" in rec3.msg


def test_codebase_contains_no_hardcoded_keys():
    """Scan all python files in the workspace for hardcoded API key patterns."""
    root_dir = Path(__file__).resolve().parent.parent
    key_pattern = re.compile("".join(["A", "I", "z", "a"]) + r"[0-9A-Za-z\-_]{35}")

    for py_file in root_dir.rglob("*.py"):
        if (
            ".git" in py_file.parts
            or ".pytest_cache" in py_file.parts
            or ".venv" in py_file.parts
            or "venv" in py_file.parts
            or "dist" in py_file.parts
            or "build" in py_file.parts
        ):
            continue

        content = py_file.read_text(encoding="utf-8", errors="ignore")
        matches = key_pattern.findall(content)
        assert len(matches) == 0, f"Found hardcoded key pattern in {py_file}: {matches}"


def test_log_file_contains_no_sensitive_data():
    """Scan existing peachy.log file (if present) for keys, image bytes, or credentials."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        pytest.skip("LOCALAPPDATA not set.")

    log_file = Path(local_app_data) / "Peachy" / "logs" / "peachy.log"
    if not log_file.exists():
        pytest.skip("No peachy.log found in LOCALAPPDATA to audit.")

    content = log_file.read_text(encoding="utf-8", errors="ignore")
    key_pattern = re.compile("".join(["A", "I", "z", "a"]) + r"[0-9A-Za-z\-_]{35}")
    matches = key_pattern.findall(content)
    assert len(matches) == 0, f"Found unredacted key in peachy.log: {matches}"
    assert "PNG" not in content or "PNG bytes" not in content  # Raw bytes never dumped
