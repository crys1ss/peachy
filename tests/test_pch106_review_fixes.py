"""Tests verifying the fixes requested from the PCH-104 review:
1. HistoryStore._migrate_v1_to_v2 logs at ERROR (not WARNING) and skips migration
   if .v1.bak file copy fails.
2. AppController.on_crop_confirmed in attach mode does not set self._current_image_bytes
   or modify overlay conversation state.
3. app.py --fake-provider flag instantiates FakeProvider.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QObject
from PySide6.QtGui import QImage
import pytest

from core.app_controller import AppController
from core.state_manager import AppState, StateManager
from history.store import HistoryStore
from tests.fakes.fake_provider import FakeProvider


def test_migration_aborts_and_logs_error_if_bak_fails(tmp_path, caplog):
    """If .v1.bak copy fails, log at ERROR and skip migration for this run."""
    db_path = tmp_path / "history.db"

    # Create a real v1 schema database
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                has_image INTEGER NOT NULL DEFAULT 0,
                image_thumbnail BLOB
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY
            );
            """
        )
        conn.execute("INSERT INTO schema_version (version) VALUES (1);")
        conn.commit()

    # Patch shutil.copy2 to raise an error simulating disk write / permission failure
    with patch("shutil.copy2", side_effect=PermissionError("Disk write permission denied")):
        with caplog.at_level(logging.ERROR):
            store = HistoryStore(db_path=db_path)

            # Check that an ERROR was logged
            error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
            assert any(
                "Skipping migration to protect user data" in r.message
                or "Failed to create pre-migration backup" in r.message
                for r in error_records
            ), f"Expected ERROR log about backup failure, got: {[r.message for r in error_records]}"

            # Verify schema was NOT upgraded
            with store.connect() as conn:
                cur = conn.execute("SELECT version FROM schema_version LIMIT 1;")
                ver = cur.fetchone()[0]
                assert ver == 1, "Schema version should remain 1 when backup copy fails"

                cur = conn.execute("PRAGMA table_info(conversations);")
                cols = {r["name"] for r in cur.fetchall()}
                assert "pinned" not in cols, "pinned column must not be added when migration is aborted"


def test_on_crop_confirmed_attach_mode_state_isolation(qapp):
    """In attachment mode, on_crop_confirmed must not modify self._current_image_bytes or overlay state."""
    state_mgr = StateManager()
    state_mgr.transition_to(AppState.SELECTING)

    hotkey_mgr = MagicMock()
    tray_mgr = MagicMock()
    overlay_mgr = MagicMock()
    popup = MagicMock()

    controller = AppController(
        state_manager=state_mgr,
        hotkey_manager=hotkey_mgr,
        tray_manager=tray_mgr,
        overlay_manager=overlay_mgr,
        popup=popup,
    )

    # Set initial overlay state
    controller._current_image_bytes = b"existing_overlay_screenshot"
    controller._current_history = [{"role": "user", "text": "prior question"}]
    controller._current_conversation_id = 42

    # Enable attachment capture mode
    controller._capturing_for_attachment = True

    # Capture signal
    captured_payloads = []
    controller.attachment_captured.connect(lambda b: captured_payloads.append(b))

    # Send a new crop
    new_crop_img = QImage(10, 10, QImage.Format.Format_RGB32)
    new_crop_img.fill(0xFF00FF)

    controller.on_crop_confirmed(new_crop_img)

    # 1. Attachment signal was emitted with image bytes
    assert len(captured_payloads) == 1
    assert isinstance(captured_payloads[0], bytes)
    assert len(captured_payloads[0]) > 0

    # 2. _capturing_for_attachment reset to False
    assert controller._capturing_for_attachment is False

    # 3. State returned to IDLE
    assert state_mgr.state == AppState.IDLE

    # 4. _current_image_bytes was NOT overwritten!
    assert controller._current_image_bytes == b"existing_overlay_screenshot"

    # 5. Overlay conversation state was NOT wiped!
    assert controller._current_conversation_id == 42
    assert len(controller._current_history) == 1

    # 6. Popup was not opened in Ask view
    popup.show_ask.assert_not_called()


def test_fake_provider_cli_flag(monkeypatch):
    """Passing --fake-provider flag instantiates FakeProvider."""
    from app import PeachyApp

    with monkeypatch.context() as m:
        m.setattr(sys, "argv", ["app.py", "--fake-provider"])
        mock_qapp = MagicMock()
        mock_server = MagicMock()

        with patch("app.TrayManager"), patch("app.OverlayManager"), \
             patch("app.PeachyPopup"), patch("app.HistoryWindow"), \
             patch("app.SettingsWindow"), patch("app.HotkeyManager"), \
             patch("app.DoubleTapHook"), patch("app.get_sound_manager"):

            app_inst = PeachyApp(mock_qapp, mock_server)
            assert isinstance(app_inst.provider, FakeProvider)
