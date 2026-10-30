"""Comprehensive tests for chat history module: store, UI, integration, and security."""

from __future__ import annotations

import io
import re
import time
from pathlib import Path
from typing import Any, List, Optional
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QMessageBox
import pytest

from ai.provider import AnswerResult, BaseAIProvider
from capture.selection_overlay import OverlayManager
from config.settings import Settings
from core.app_controller import AppController
from core.hotkey_manager import HotkeyManager, parse_shortcut
from core.state_manager import AppState, StateManager
from history.store import (
    HistoryStore,
    create_thumbnail,
    generate_title,
    get_default_history_db_path,
)
from history.worker import HistoryDbWorker
from ui.history_window import HistoryWindow
from ui.peachy_popup import PeachyPopup
from ui.tray_manager import TrayManager


class FakeAIProvider(BaseAIProvider):
    """Fake AI provider for offline testing."""

    def __init__(self, response_text: str = "Fake response text"):
        self.response_text = response_text
        self.call_count = 0
        self.last_image_png = None
        self.last_question = None
        self.last_history = None

    def ask(
        self,
        image_png: Optional[bytes],
        question: str,
        history: Optional[List[Any]] = None,
    ) -> AnswerResult:
        self.call_count += 1
        self.last_image_png = image_png
        self.last_question = question
        self.last_history = history

        new_history = list(history or [])
        new_history.append({"role": "user", "parts": [question]})
        new_history.append({"role": "model", "parts": [self.response_text]})
        return AnswerResult(text=self.response_text, history=new_history)


# ---------------------------------------------------------------------------
# 1. Title generation
# ---------------------------------------------------------------------------
def test_title_generation():
    """Verify title generation for question provided and for no-question fallback."""
    # Case 1: Question provided <= 50 chars
    assert generate_title("How do I parse JSON in Python?", "You use json.loads()") == "How do I parse JSON in Python?"

    # Case 1: Question provided > 50 chars cut at 50 characters
    long_q = "How do I parse extremely nested JSON structures in modern Python 3.12 without crashing?"
    assert len(generate_title(long_q, "Answer")) == 50
    assert generate_title(long_q, "Answer") == long_q[:50]

    # Case 2: No question provided (empty string, None, or default prompt)
    # First six words of the first answer
    ans = "This is a detailed error message explaining why the build failed completely"
    assert generate_title("", ans) == "This is a detailed error message"
    assert generate_title(None, ans) == "This is a detailed error message"
    assert generate_title("Explain this screen", ans) == "This is a detailed error message"

    # Short answer fallback
    short_ans = "Error code 404"
    assert generate_title("", short_ans) == "Error code 404"

    # Both empty fallback
    assert generate_title("", "") == "New Conversation"


# ---------------------------------------------------------------------------
# 2. Thumbnail generation
# ---------------------------------------------------------------------------
def test_create_thumbnail():
    """Verify thumbnail is 240px wide JPEG quality 70."""
    # Create test image 480x320 PNG bytes
    img = QImage(480, 320, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 100, 100))
    buffer = io.BytesIO()
    # Save as PNG
    from PySide6.QtCore import QBuffer, QIODevice
    qbuf = QBuffer()
    qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(qbuf, "PNG")
    png_bytes = bytes(qbuf.data())

    thumb_bytes = create_thumbnail(png_bytes)
    assert thumb_bytes is not None
    # Check that thumb starts with JPEG header
    assert thumb_bytes[:2] == b"\xff\xd8"

    # Read thumb back to check width
    thumb_img = QImage.fromData(thumb_bytes)
    assert thumb_img.width() == 240
    assert thumb_img.height() == 160


# ---------------------------------------------------------------------------
# 3. Store CRUD: create, append, list order, search, delete, clear_all
# ---------------------------------------------------------------------------
def test_history_store_crud(tmp_path: Path):
    """Test full CRUD operations on HistoryStore."""
    db_file = tmp_path / "test_history.db"
    store = HistoryStore(db_path=db_file)

    # Initially empty
    assert len(store.list_conversations()) == 0

    # Create conv 1
    c1_id = store.create_conversation("First Chat Title")
    assert c1_id > 0
    store.add_message(c1_id, "user", "What is Python?", has_image=True)
    store.add_message(c1_id, "assistant", "Python is a programming language.")

    # Small delay to ensure timestamp diff for sorting
    time.sleep(0.05)

    # Create conv 2
    c2_id = store.create_conversation("Second Chat Title")
    store.add_message(c2_id, "user", "Explain SQLite WAL mode.")
    store.add_message(c2_id, "assistant", "WAL stands for Write-Ahead Logging.")

    # List conversations - ordered by updated_at DESC (c2 should be first)
    convs = store.list_conversations()
    assert len(convs) == 2
    assert convs[0]["id"] == c2_id
    assert convs[0]["title"] == "Second Chat Title"
    assert convs[1]["id"] == c1_id
    assert convs[1]["title"] == "First Chat Title"

    # Get conversation details
    c1 = store.get_conversation(c1_id)
    assert c1 is not None
    assert c1["title"] == "First Chat Title"

    # Get messages
    msgs_c1 = store.get_messages(c1_id)
    assert len(msgs_c1) == 2
    assert msgs_c1[0]["role"] == "user"
    assert msgs_c1[0]["text"] == "What is Python?"
    assert msgs_c1[0]["has_image"] == 1
    assert msgs_c1[1]["role"] == "assistant"
    assert msgs_c1[1]["text"] == "Python is a programming language."

    # Search conversations (SQL LIKE over message text)
    res_wal = store.search_conversations("WAL")
    assert len(res_wal) == 1
    assert res_wal[0]["id"] == c2_id

    res_py = store.search_conversations("Python")
    assert len(res_py) == 1
    assert res_py[0]["id"] == c1_id

    res_none = store.search_conversations("NonexistentQuery")
    assert len(res_none) == 0

    # Delete one conversation
    assert store.delete_conversation(c1_id) is True
    assert len(store.list_conversations()) == 1
    assert store.get_conversation(c1_id) is None
    assert len(store.get_messages(c1_id)) == 0

    # Clear all
    assert store.clear_all() is True
    assert len(store.list_conversations()) == 0


# ---------------------------------------------------------------------------
# 4. Corrupt database recovery
# ---------------------------------------------------------------------------
def test_corrupt_database_recovery(tmp_path: Path):
    """Corrupt database file is backed up to .bak, recreated at original path, and keeps store.db_path."""
    db_file = tmp_path / "corrupt_history.db"
    bak_file = tmp_path / "corrupt_history.db.bak"

    # Write corrupt data
    db_file.write_bytes(b"THIS IS CORRUPT NON-SQLITE DATA BUFFER 1234567890")

    # Initializing store should recover safely
    store = HistoryStore(db_path=db_file)

    # 1. The corrupt database is backed up
    assert bak_file.exists()
    assert bak_file.read_bytes() == b"THIS IS CORRUPT NON-SQLITE DATA BUFFER 1234567890"

    # 2. Original database path is preserved (NOT redirected to temp fallback)
    assert store.db_path == db_file
    assert db_file.exists()

    # 3. The recreated database has a valid schema and version
    with store.connect() as conn:
        cur = conn.execute("SELECT version FROM schema_version LIMIT 1;")
        row = cur.fetchone()
        assert row is not None
        assert row["version"] == 1

        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
        assert {"schema_version", "conversations", "messages"}.issubset(tables)

    # 4. Conversations can be saved and retrieved after recovery
    cid = store.create_conversation("Recovered DB Conv")
    assert cid > 0
    store.add_message(cid, "user", "Hello again")
    convs = store.list_conversations()
    assert len(convs) == 1
    assert convs[0]["id"] == cid
    assert convs[0]["title"] == "Recovered DB Conv"
    msgs = store.get_messages(cid)
    assert len(msgs) == 1
    assert msgs[0]["text"] == "Hello again"


# ---------------------------------------------------------------------------
# 5. Export produces valid Markdown
# ---------------------------------------------------------------------------
def test_export_markdown(tmp_path: Path):
    """Verify export_markdown produces structured, readable markdown."""
    db_file = tmp_path / "export_test.db"
    store = HistoryStore(db_path=db_file)
    cid = store.create_conversation("System Architecture Discussion")
    store.add_message(cid, "user", "How does the SQLite WAL mode work?")
    store.add_message(cid, "assistant", "WAL mode writes changes to a separate `-wal` file before checkpointing.")

    md = store.export_markdown(cid)
    assert "# System Architecture Discussion" in md
    assert "### You" in md
    assert "How does the SQLite WAL mode work?" in md
    assert "### Peachy" in md
    assert "WAL mode writes changes to a separate `-wal` file" in md


# ---------------------------------------------------------------------------
# 6. Database privacy: no key-shaped strings and no screenshots when thumbnails off
# ---------------------------------------------------------------------------
def test_database_privacy_audit(tmp_path: Path):
    """Ensure database contents contain no keys or raw screenshots when thumbnails are off."""
    db_file = tmp_path / "privacy_test.db"
    store = HistoryStore(db_path=db_file)

    cid = store.create_conversation("Test Conversation")
    store.add_message(cid, "user", "What is my API key status?", has_image=True)
    store.add_message(cid, "assistant", "Your API key is configured and active.")

    # Read all raw bytes from DB file
    raw_data = db_file.read_bytes()

    # Verify no Gemini key pattern
    key_pattern = re.compile(b"".join([b"A", b"I", b"z", b"a"]) + b"[0-9A-Za-z\\-_]{35}|" + b"".join([b"A", b"Q", b"."]) + b"[A-Za-z0-9_-]{20,}")
    assert not key_pattern.search(raw_data)

    # Verify no raw PNG or JPEG images stored
    conv = store.get_conversation(cid)
    assert conv["thumbnail"] is None


# ---------------------------------------------------------------------------
# 7. Saving off means nothing is written; thumbnails off by default
# ---------------------------------------------------------------------------
def test_saving_off_writes_nothing(tmp_path: Path, qtbot):
    """When save_history is False, no conversation or message is written to DB."""
    db_file = tmp_path / "opt_in_test.db"
    store = HistoryStore(db_path=db_file)
    settings = Settings(save_history=False, save_thumbnails=False, save_history_prompted=True)

    state_mgr = StateManager()
    hotkey_mgr = HotkeyManager()
    tray_mgr = TrayManager()
    overlay_mgr = OverlayManager()
    popup = PeachyPopup()
    provider = FakeAIProvider("Test answer text")

    controller = AppController(
        state_manager=state_mgr,
        hotkey_manager=hotkey_mgr,
        tray_manager=tray_mgr,
        overlay_manager=overlay_mgr,
        popup=popup,
        provider=provider,
        settings=settings,
        history_store=store,
    )
    qtbot.addWidget(popup)

    # Transition to ASKING via selection crop
    state_mgr.transition_to(AppState.CAPTURING)
    state_mgr.transition_to(AppState.SELECTING)
    img = QImage(120, 80, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 0, 0))
    controller.overlay_manager.last_selection_rect = QRect(100, 100, 120, 80)
    controller.on_crop_confirmed(img)

    assert state_mgr.state == AppState.ASKING
    controller.on_send_question("What is this?")
    qtbot.waitUntil(lambda: state_mgr.state == AppState.ANSWERING, timeout=2000)

    # Confirm store is still completely empty
    assert len(store.list_conversations()) == 0

    popup.close()
    controller.shutdown()


def test_saving_on_writes_conversation_and_messages(tmp_path: Path, qtbot):
    """When save_history is True, completed turns are saved."""
    db_file = tmp_path / "saving_on_test.db"
    store = HistoryStore(db_path=db_file)
    settings = Settings(save_history=True, save_thumbnails=False, save_history_prompted=True)

    state_mgr = StateManager()
    hotkey_mgr = HotkeyManager()
    tray_mgr = TrayManager()
    overlay_mgr = OverlayManager()
    popup = PeachyPopup()
    provider = FakeAIProvider("Saved answer text")

    controller = AppController(
        state_manager=state_mgr,
        hotkey_manager=hotkey_mgr,
        tray_manager=tray_mgr,
        overlay_manager=overlay_mgr,
        popup=popup,
        provider=provider,
        settings=settings,
        history_store=store,
    )
    qtbot.addWidget(popup)

    state_mgr.transition_to(AppState.CAPTURING)
    state_mgr.transition_to(AppState.SELECTING)
    img = QImage(120, 80, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 0, 0))
    controller.overlay_manager.last_selection_rect = QRect(100, 100, 120, 80)
    controller.on_crop_confirmed(img)

    assert state_mgr.state == AppState.ASKING
    controller.on_send_question("Save this turn")
    qtbot.waitUntil(lambda: state_mgr.state == AppState.ANSWERING, timeout=2000)
    qtbot.waitUntil(
        lambda: len(store.list_conversations()) == 1
        and len(store.get_messages(store.list_conversations()[0]["id"])) == 2,
        timeout=3000,
    )

    convs = store.list_conversations()
    assert len(convs) == 1
    assert convs[0]["title"] == "Save this turn"
    assert convs[0]["thumbnail"] is None

    msgs = store.get_messages(convs[0]["id"])
    assert len(msgs) == 2
    assert msgs[0]["text"] == "Save this turn"
    assert msgs[1]["text"] == "Saved answer text"

    popup.close()
    controller.shutdown()


# ---------------------------------------------------------------------------
# 8. Continue builds the right history for the provider (last 20 messages)
# ---------------------------------------------------------------------------
def test_continue_chat_last_20_messages(tmp_path: Path, qtbot):
    """Verify 'Continue this chat' builds the last 20 messages and sets note."""
    db_file = tmp_path / "continue_test.db"
    store = HistoryStore(db_path=db_file)
    cid = store.create_conversation("Long Multi-Turn Conversation")

    # Add 26 messages (13 turns)
    for i in range(13):
        store.add_message(cid, "user", f"Question {i+1}")
        store.add_message(cid, "assistant", f"Answer {i+1}")

    settings = Settings(save_history=True)
    state_mgr = StateManager()
    hotkey_mgr = HotkeyManager()
    tray_mgr = TrayManager()
    overlay_mgr = OverlayManager()
    popup = PeachyPopup()
    provider = FakeAIProvider("Followup response")

    controller = AppController(
        state_manager=state_mgr,
        hotkey_manager=hotkey_mgr,
        tray_manager=tray_mgr,
        overlay_manager=overlay_mgr,
        popup=popup,
        provider=provider,
        settings=settings,
        history_store=store,
    )
    qtbot.addWidget(popup)

    # Continue conversation
    controller.continue_conversation(cid)

    # Verify popup state and note
    assert controller._current_conversation_id == cid
    assert len(controller._current_history) == 20
    # First message in history should be Question 4 (since total was 26: 26 - 20 = index 6 which is Question 4)
    first_hist = controller._current_history[0]
    if isinstance(first_hist, dict):
        assert first_hist["parts"][0] == "Question 4"
    else:
        assert first_hist.parts[0].text == "Question 4"

    # Note label should be visible
    assert popup.answer_view.note_label.isVisible() is True
    assert "Earlier screenshots are not re-sent." in popup.answer_view.note_label.text()

    # Perform a followup and verify last_history passed to provider contains the 20 messages
    controller.on_send_followup("Followup question 14")
    qtbot.waitUntil(lambda: provider.call_count == 1, timeout=2000)

    assert len(provider.last_history) == 20
    assert provider.last_question == "Followup question 14"

    popup.close()
    controller.shutdown()


# ---------------------------------------------------------------------------
# 9. Opening History in SELECTING is ignored
# ---------------------------------------------------------------------------
def test_open_history_ignored_in_selecting(tmp_path: Path, qtbot):
    """Opening history while in SELECTING state is ignored and does not disturb FSM."""
    db_file = tmp_path / "fsm_test.db"
    store = HistoryStore(db_path=db_file)
    settings = Settings()

    state_mgr = StateManager()
    hotkey_mgr = HotkeyManager()
    tray_mgr = TrayManager()
    overlay_mgr = OverlayManager()
    popup = PeachyPopup()
    history_win = HistoryWindow(store=store, settings=settings)

    controller = AppController(
        state_manager=state_mgr,
        hotkey_manager=hotkey_mgr,
        tray_manager=tray_mgr,
        overlay_manager=overlay_mgr,
        popup=popup,
        settings=settings,
        history_store=store,
        history_window=history_win,
    )
    qtbot.addWidget(popup)
    qtbot.addWidget(history_win)

    # Force state to SELECTING via valid FSM path
    state_mgr.transition_to(AppState.CAPTURING)
    state_mgr.transition_to(AppState.SELECTING)
    assert state_mgr.state == AppState.SELECTING

    # Attempt to open history
    controller.open_history()

    # State must not have changed and history window must not be shown
    assert state_mgr.state == AppState.SELECTING
    assert history_win.isVisible() is False

    # In IDLE state, open_history works
    state_mgr.reset_to_idle()
    controller.open_history()
    assert history_win.isVisible() is True
    assert state_mgr.state == AppState.IDLE

    history_win.close()
    popup.close()
    controller.shutdown()


# ---------------------------------------------------------------------------
# 10. Opt-in prompt banner on first completed answer
# ---------------------------------------------------------------------------
def test_opt_in_prompt_banner(tmp_path: Path, qtbot):
    """First completed answer prompts user; choice is remembered."""
    db_file = tmp_path / "banner_test.db"
    store = HistoryStore(db_path=db_file)
    settings = Settings(save_history=False, save_history_prompted=False)

    state_mgr = StateManager()
    hotkey_mgr = HotkeyManager()
    tray_mgr = TrayManager()
    overlay_mgr = OverlayManager()
    popup = PeachyPopup()
    provider = FakeAIProvider("First completion answer")

    controller = AppController(
        state_manager=state_mgr,
        hotkey_manager=hotkey_mgr,
        tray_manager=tray_mgr,
        overlay_manager=overlay_mgr,
        popup=popup,
        provider=provider,
        settings=settings,
        history_store=store,
    )
    qtbot.addWidget(popup)

    with patch("config.settings.save_settings") as mock_save:
        state_mgr.transition_to(AppState.CAPTURING)
        state_mgr.transition_to(AppState.SELECTING)
        img = QImage(120, 80, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 0, 0))
        controller.overlay_manager.last_selection_rect = QRect(100, 100, 120, 80)
        controller.on_crop_confirmed(img)

        controller.on_send_question("Initial question")
        qtbot.waitUntil(lambda: state_mgr.state == AppState.ANSWERING, timeout=2000)

        # Opt-in prompt banner must be shown
        assert popup.answer_view.opt_in_banner.isVisible() is True

        # User clicks "Save"
        popup.opt_in_choice.emit(True)
        qtbot.waitUntil(lambda: len(store.list_conversations()) == 1, timeout=2000)

        assert settings.save_history is True
        assert settings.save_history_prompted is True
        assert popup.answer_view.opt_in_banner.isVisible() is False
        mock_save.assert_called()

        # Check conversation was saved
        convs = store.list_conversations()
        assert len(convs) == 1
        assert convs[0]["title"] == "Initial question"

    popup.close()
    controller.shutdown()


# ---------------------------------------------------------------------------
# 11. HistoryWindow UI: grouping, search, delete, clear all, continue
# ---------------------------------------------------------------------------
def test_history_window_ui(tmp_path: Path, qtbot):
    """Test HistoryWindow UI components and interactions."""
    db_file = tmp_path / "ui_test.db"
    store = HistoryStore(db_path=db_file)
    settings = Settings(save_history=True)

    cid1 = store.create_conversation("Chat 1")
    store.add_message(cid1, "user", "Question about Python")
    store.add_message(cid1, "assistant", "Python is great.")

    time.sleep(0.05)

    cid2 = store.create_conversation("Chat 2")
    store.add_message(cid2, "user", "Question about Rust")
    store.add_message(cid2, "assistant", "Rust is fast.")

    win = HistoryWindow(store=store, settings=settings)
    qtbot.addWidget(win)

    win.refresh()
    assert win.tree.topLevelItemCount() > 0

    # Search filter
    win.search_edit.setText("Rust")
    assert win.tree.topLevelItemCount() > 0

    # Clear search
    win.search_edit.setText("")

    # Select Chat 1
    target_item = None
    for i in range(win.tree.topLevelItemCount()):
        grp = win.tree.topLevelItem(i)
        for j in range(grp.childCount()):
            child = grp.child(j)
            if child.data(0, Qt.ItemDataRole.UserRole) == cid1:
                target_item = child
                break
    assert target_item is not None
    win._load_conversation_transcript(cid1)

    # Transcript should show conversation title and bubbles
    assert win.conv_title_label.text() == "Chat 1"
    assert win.messages_layout.count() >= 2

    # Test Continue chat button signal
    continue_spy = []
    win.continue_chat_requested.connect(continue_spy.append)
    win.btn_continue.click()
    assert len(continue_spy) == 1
    assert continue_spy[0] == cid1

    # Test Delete chat button
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        win.btn_delete.click()
        assert store.get_conversation(cid1) is None

    # Test Clear all button
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        win.btn_clear_all.click()
        assert len(store.list_conversations()) == 0
        assert win.right_stack.currentIndex() == 0

    win.close()


# ---------------------------------------------------------------------------
# 12. PCH-101 Regression Tests: HistoryStore Isolation & Worker Concurrency
# ---------------------------------------------------------------------------
def test_history_store_custom_env_var_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Regression test: PEACHY_HISTORY_DB_PATH overrides default APPDATA location."""
    custom_db = tmp_path / "custom_env_override.db"
    monkeypatch.setenv("PEACHY_HISTORY_DB_PATH", str(custom_db))

    store = HistoryStore()
    assert store.db_path == custom_db
    cid = store.create_conversation("Env Override Test")
    assert cid > 0
    assert custom_db.exists()


def test_history_store_inaccessible_path_fallback(tmp_path: Path):
    """Regression test: Inaccessible or invalid DB paths recover to temp DB without raising."""
    invalid_path = Path("Z:\\nonexistent_drive_peachy_test_123\\history.db")
    store = HistoryStore(db_path=invalid_path)

    # Should have recovered to fallback temp DB without crashing
    assert store.db_path != invalid_path
    assert "fallback" in store.db_path.name or store.db_path.exists()
    cid = store.create_conversation("Fallback Path Test")
    assert cid > 0
    conv = store.get_conversation(cid)
    assert conv is not None
    assert conv["title"] == "Fallback Path Test"


def test_history_worker_concurrent_save(tmp_path: Path, qtbot):
    """Regression test: Ensure sequential background worker turns commit without race conditions."""
    db_file = tmp_path / "concurrent_save_test.db"
    store = HistoryStore(db_path=db_file)
    settings = Settings(save_history=True, save_thumbnails=False, save_history_prompted=True)

    state_mgr = StateManager()
    hotkey_mgr = HotkeyManager()
    tray_mgr = TrayManager()
    overlay_mgr = OverlayManager()
    popup = PeachyPopup()
    provider = FakeAIProvider("Turn response")

    controller = AppController(
        state_manager=state_mgr,
        hotkey_manager=hotkey_mgr,
        tray_manager=tray_mgr,
        overlay_manager=overlay_mgr,
        popup=popup,
        provider=provider,
        settings=settings,
        history_store=store,
    )
    qtbot.addWidget(popup)

    state_mgr.transition_to(AppState.CAPTURING)
    state_mgr.transition_to(AppState.SELECTING)
    img = QImage(120, 80, QImage.Format.Format_RGB32)
    img.fill(QColor(0, 255, 0))
    controller.overlay_manager.last_selection_rect = QRect(0, 0, 120, 80)
    controller.on_crop_confirmed(img)

    controller.on_send_question("Turn 1 Question")
    qtbot.waitUntil(
        lambda: len(store.list_conversations()) == 1
        and len(store.get_messages(store.list_conversations()[0]["id"])) == 2,
        timeout=3000,
    )

    # Send a follow-up
    controller.on_send_followup("Turn 2 Question")
    cid = store.list_conversations()[0]["id"]
    qtbot.waitUntil(lambda: len(store.get_messages(cid)) == 4, timeout=3000)

    msgs = store.get_messages(cid)
    assert len(msgs) == 4
    assert msgs[0]["text"] == "Turn 1 Question"
    assert msgs[1]["text"] == "Turn response"
    assert msgs[2]["text"] == "Turn 2 Question"
    assert msgs[3]["text"] == "Turn response"

    popup.close()
    controller.shutdown()



def test_corrupt_database_recovery_failure_does_not_falsely_report_success(tmp_path: Path):
    """A failed recovery (e.g. file lock or permissions) returns False and does not falsely report success."""
    db_file = tmp_path / "locked_corrupt.db"
    db_file.write_bytes(b"CORRUPT DATA")

    store = HistoryStore.__new__(HistoryStore)
    store.db_path = db_file

    # Simulate unlink failure (e.g. file locked by another process)
    with patch.object(Path, "unlink", side_effect=OSError("Permission denied: file in use")):
        res = store._recover_corrupt_db()
        assert res is False


def test_normal_production_database_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Test normal production APPDATA path resolution without relying exclusively on autouse fixture."""
    monkeypatch.delenv("PEACHY_HISTORY_DB_PATH", raising=False)
    fake_appdata = tmp_path / "FakeProductionAppData"
    monkeypatch.setenv("APPDATA", str(fake_appdata))

    default_path = get_default_history_db_path()
    expected_path = fake_appdata / "Peachy" / "history.db"
    assert default_path == expected_path

    # Initializing with default path creates the production DB at expected path
    store = HistoryStore()
    assert store.db_path == expected_path
    assert expected_path.exists()
    cid = store.create_conversation("Production DB Test")
    assert cid > 0
    conv = store.get_conversation(cid)
    assert conv is not None
    assert conv["title"] == "Production DB Test"


# ---------------------------------------------------------------------------
# 12. PCH-101 Hardening: Strict recovery, backup integrity, concurrency, fallback
# ---------------------------------------------------------------------------
def test_recovery_fails_on_wal_deletion_failure(tmp_path: Path):
    """Strict recovery: fails and returns False if the -wal companion file cannot be unlinked."""
    import os
    db_file = tmp_path / "corrupt_wal_fail.db"
    wal_file = tmp_path / "corrupt_wal_fail.db-wal"
    db_file.write_bytes(b"CORRUPT DB")
    wal_file.write_bytes(b"WAL DATA")

    store = HistoryStore.__new__(HistoryStore)
    store.db_path = db_file

    orig_unlink = os.unlink

    def mock_unlink(path, *args, **kwargs):
        if str(path).endswith("-wal"):
            raise OSError("Locked: cannot unlink WAL")
        return orig_unlink(path, *args, **kwargs)

    with patch("os.unlink", side_effect=mock_unlink):
        success = store._recover_corrupt_db()
        assert success is False


def test_recovery_fails_on_shm_deletion_failure(tmp_path: Path):
    """Strict recovery: fails and returns False if the -shm companion file cannot be unlinked."""
    import os
    db_file = tmp_path / "corrupt_shm_fail.db"
    shm_file = tmp_path / "corrupt_shm_fail.db-shm"
    db_file.write_bytes(b"CORRUPT DB")
    shm_file.write_bytes(b"SHM DATA")

    store = HistoryStore.__new__(HistoryStore)
    store.db_path = db_file

    orig_unlink = os.unlink

    def mock_unlink(path, *args, **kwargs):
        if str(path).endswith("-shm"):
            raise OSError("Locked: cannot unlink SHM")
        return orig_unlink(path, *args, **kwargs)

    with patch("os.unlink", side_effect=mock_unlink):
        success = store._recover_corrupt_db()
        assert success is False


def test_recovery_fails_on_main_db_deletion_failure(tmp_path: Path):
    """Strict recovery: fails and returns False if the main database file cannot be unlinked."""
    import os
    db_file = tmp_path / "corrupt_main_fail.db"
    db_file.write_bytes(b"CORRUPT DB")

    store = HistoryStore.__new__(HistoryStore)
    store.db_path = db_file

    orig_unlink = os.unlink

    def mock_unlink(path, *args, **kwargs):
        if str(path) == str(db_file):
            raise OSError("Locked: cannot unlink main database")
        return orig_unlink(path, *args, **kwargs)

    with patch("os.unlink", side_effect=mock_unlink):
        success = store._recover_corrupt_db()
        assert success is False


def test_concurrent_recovery_protection(tmp_path: Path):
    """Concurrent recovery attempts by multiple threads are safely serialized by _RECOVERY_LOCK."""
    import threading

    db_file = tmp_path / "concurrent_corrupt.db"
    db_file.write_bytes(b"NOT A VALID SQLITE DATABASE -- FORCE CORRUPTION ERROR")

    errors: list[Exception] = []
    stores: list[HistoryStore] = []

    def worker():
        try:
            s = HistoryStore(db_path=db_file)
            stores.append(s)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent recovery threw unexpected errors: {errors}"
    assert len(stores) == 6

    # All stores should have resolved to the original database path without activating fallback
    for s in stores:
        assert s.db_path == db_file
        assert not s.is_fallback

    # The recovered database should be healthy and support writes/reads
    primary_store = stores[0]
    cid = primary_store.create_conversation("Concurrent Recovery Post-Test")
    assert cid > 0
    msgs = primary_store.get_messages(cid)
    assert msgs == []


def test_backup_preserves_all_wal_and_shm_artifacts(tmp_path: Path):
    """SQLite backup integrity: recovery preserves history.db, -wal, and -shm files to .bak."""
    db_file = tmp_path / "corrupt_wal_shm.db"
    wal_file = tmp_path / "corrupt_wal_shm.db-wal"
    shm_file = tmp_path / "corrupt_wal_shm.db-shm"

    db_bytes = b"CORRUPT MAIN DATABASE BYTES"
    wal_bytes = b"CRITICAL UNCHECKPOINTED WAL TRANSACTIONS 12345"
    shm_bytes = b"SHARED MEMORY INDEX 67890"

    db_file.write_bytes(db_bytes)
    wal_file.write_bytes(wal_bytes)
    shm_file.write_bytes(shm_bytes)

    store = HistoryStore(db_path=db_file)

    # All 3 .bak companion files must exist with exact byte integrity
    db_bak = tmp_path / "corrupt_wal_shm.db.bak"
    wal_bak = tmp_path / "corrupt_wal_shm.db-wal.bak"
    shm_bak = tmp_path / "corrupt_wal_shm.db-shm.bak"

    assert db_bak.exists()
    assert db_bak.read_bytes() == db_bytes

    assert wal_bak.exists()
    assert wal_bak.read_bytes() == wal_bytes

    assert shm_bak.exists()
    assert shm_bak.read_bytes() == shm_bytes

    # The store successfully restored the database at original path
    assert store.db_path == db_file
    assert not store.is_fallback


def test_recovery_with_existing_wal_data(tmp_path: Path):
    """Corrupt DB with active WAL data backs up both, recreates clean schema, and supports CRUD."""
    db_file = tmp_path / "active_wal_store.db"
    wal_file = tmp_path / "active_wal_store.db-wal"

    db_file.write_bytes(b"CORRUPTED HEADER")
    wal_file.write_bytes(b"WAL DATA BEFORE CRASH")

    store = HistoryStore(db_path=db_file)

    # Verify backup preserved WAL
    wal_bak = tmp_path / "active_wal_store.db-wal.bak"
    assert wal_bak.exists()
    assert wal_bak.read_bytes() == b"WAL DATA BEFORE CRASH"

    # Verify store can execute normal operations
    cid = store.create_conversation("Fresh After WAL Recovery")
    assert cid > 0
    store.add_message(cid, "user", "Message after WAL recovery")
    store.add_message(cid, "assistant", "Database restored cleanly.")

    convs = store.list_conversations()
    assert len(convs) == 1
    assert convs[0]["title"] == "Fresh After WAL Recovery"

    messages = store.get_messages(cid)
    assert len(messages) == 2
    assert messages[0]["text"] == "Message after WAL recovery"
    assert messages[1]["text"] == "Database restored cleanly."


def test_temporary_fallback_notification_and_flag(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    """When permanent path cannot be recovered, HistoryStore enters non-silent fallback mode."""
    import logging

    db_file = tmp_path / "unusable.db"
    db_file.write_bytes(b"CORRUPT DATA")

    notifications: list[str] = []

    def on_fallback_callback(reason: str) -> None:
        notifications.append(reason)

    # Force recovery to fail (e.g. disk write-protection or locked corrupt file)
    with patch.object(HistoryStore, "_recover_corrupt_db", return_value=False):
        with caplog.at_level(logging.ERROR):
            store = HistoryStore(db_path=db_file, on_fallback=on_fallback_callback)

    # 1. Store flags it is in fallback mode
    assert store.is_fallback is True
    assert store.fallback_reason is not None
    assert "Recovery failed" in store.fallback_reason

    # 2. Callback was invoked
    assert len(notifications) == 1
    assert "Recovery failed" in notifications[0]

    # 3. Store path redirected to temp fallback, original path preserved
    assert store.original_db_path == db_file
    assert store.db_path != db_file
    assert "peachy_history" in str(store.db_path)

    # 4. Original file is intact (not deleted/corrupted further)
    assert db_file.exists()
    assert db_file.read_bytes() == b"CORRUPT DATA"

    # 5. Fallback DB is operational for the session
    cid = store.create_conversation("Fallback Session Conv")
    assert cid > 0

    # 6. Prominent log message emitted
    assert any("STORAGE DEGRADED" in record.message for record in caplog.records)
    assert any("Chat history in this session will NOT persist" in record.message for record in caplog.records)
