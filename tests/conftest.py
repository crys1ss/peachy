"""Global pytest fixtures and test environment isolation for Peachy."""

from __future__ import annotations

import os
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def isolate_test_history_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Ensure any HistoryStore created without an explicit path uses a clean temporary database."""
    test_db = tmp_path / "peachy_test_auto_history.db"
    monkeypatch.setenv("PEACHY_HISTORY_DB_PATH", str(test_db))
    return test_db
