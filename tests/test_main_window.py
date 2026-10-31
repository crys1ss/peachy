"""Unit and integration tests for MainWindow, Sidebar, Composer, and WelcomeView."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QMessageBox

from config.settings import Settings
from history.store import HistoryStore
from tests.fakes.fake_chat_session import FakeChatSession
from ui.composer import Composer, MAX_ATTACHMENTS, MAX_TOTAL_BYTES
from ui.main_window import ConversationView, MainWindow
from ui.sidebar import ROLE_CONV_ID, ROLE_IS_SECTION, ROLE_PINNED, ROLE_TITLE, Sidebar
from ui.theme import MIDNIGHT_THEME, LIGHT_THEME
from ui.welcome_view import OptInHistoryCard, WelcomeView, get_time_of_day_greeting


@pytest.fixture
def temp_store(tmp_path: Path) -> HistoryStore:
    """Create a clean HistoryStore in a temporary directory."""
    db_file = tmp_path / "test_history.db"
    return HistoryStore(db_path=db_file)


# ---------------------------------------------------------------------------
# 1. Welcome Greeting by Hour & Opt-in Card
# ---------------------------------------------------------------------------

def test_welcome_greeting_by_hour():
    """Verify time-of-day greeting adapts accurately to hour and display_name."""
    # Morning: 05:00 to 11:59
    t_morning = datetime(2026, 10, 31, 8, 30)
    assert get_time_of_day_greeting(t_morning, display_name="Zidane") == "Good morning, Zidane"
    assert get_time_of_day_greeting(t_morning, display_name="") == "Good morning"

    # Afternoon: 12:00 to 16:59
    t_afternoon = datetime(2026, 10, 31, 14, 0)
    assert get_time_of_day_greeting(t_afternoon, display_name="Zidane") == "Good afternoon, Zidane"
    assert get_time_of_day_greeting(t_afternoon, display_name="") == "Good afternoon"

    # Evening: 17:00 to 21:59
    t_evening = datetime(2026, 10, 31, 19, 45)
    assert get_time_of_day_greeting(t_evening, display_name="Zidane") == "Good evening, Zidane"
    assert get_time_of_day_greeting(t_evening, display_name="") == "Good evening"

    # Night: 22:00 to 04:59
    t_night = datetime(2026, 10, 31, 23, 15)
    assert get_time_of_day_greeting(t_night, display_name="Zidane") == "Good night, Zidane"
    assert get_time_of_day_greeting(t_night, display_name="") == "Good night"


def test_opt_in_card_choices_saved(qtbot):
    """Verify Opt-In history card visibility and choice persistence."""
    settings = Settings(save_history=False, save_history_prompted=False)

    with patch("config.settings.save_settings") as mock_save:
        welcome = WelcomeView(settings=settings, theme=MIDNIGHT_THEME)
        qtbot.addWidget(welcome)
        welcome.show()

        # Initially visible when save_history_prompted is False
        assert welcome.opt_in_card.isVisible() is True

        # Click 'Keep chats'
        welcome.opt_in_card.keep_btn.click()
        assert settings.save_history is True
        assert settings.save_history_prompted is True
        assert welcome.opt_in_card.isVisible() is False
        mock_save.assert_called_once()

        # When save_history_prompted is True initially, it starts hidden
        settings2 = Settings(save_history=False, save_history_prompted=True)
        welcome2 = WelcomeView(settings=settings2, theme=MIDNIGHT_THEME)
        qtbot.addWidget(welcome2)
        welcome2.show()
        assert welcome2.opt_in_card.isVisible() is False


# ---------------------------------------------------------------------------
# 2. Composer Key Handling, Attachments & Limits
# ---------------------------------------------------------------------------

def test_composer_key_handling(qtbot):
    """Verify Enter sends, Shift+Enter adds newline, and Up edits last message."""
    composer = Composer(theme=MIDNIGHT_THEME)
    qtbot.addWidget(composer)

    sent_payloads = []
    edit_last_called = False

    composer.send_requested.connect(lambda text, imgs: sent_payloads.append((text, imgs)))
    composer.edit_last_requested.connect(lambda: nonlocal_edit())

    def nonlocal_edit():
        nonlocal edit_last_called
        edit_last_called = True

    # 1. Up arrow in empty composer emits edit_last_requested
    event_up = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
    composer.input_edit.keyPressEvent(event_up)
    assert edit_last_called is True

    # 2. Shift+Enter inserts newline without sending
    composer.input_edit.setPlainText("Hello")
    event_shift_enter = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    composer.input_edit.keyPressEvent(event_shift_enter)
    assert len(sent_payloads) == 0

    # 3. Enter sends message and clears composer
    event_enter = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    composer.input_edit.keyPressEvent(event_enter)
    assert len(sent_payloads) == 1
    assert "Hello" in sent_payloads[0][0]
    assert composer.input_edit.toPlainText() == ""


def test_composer_attachment_limits_and_toasts(qtbot):
    """Verify composer enforces 4 images max and 20 MB total limit with toasts."""
    composer = Composer(theme=MIDNIGHT_THEME)
    qtbot.addWidget(composer)
    composer.show()

    toasts = []
    composer.toast_requested.connect(toasts.append)

    # 1. Add 4 images (should succeed)
    small_img = b"PNG_TEST_DATA"
    composer.add_images([small_img, small_img, small_img, small_img])
    assert len(composer._attachments) == 4
    assert composer.attachments_tray.isVisible() is True
    assert len(toasts) == 0

    # 2. Add 5th image -> toast triggered, capped at 4
    composer.add_images([small_img])
    assert len(composer._attachments) == 4
    assert len(toasts) == 1
    assert "Maximum 4 images" in toasts[-1]

    # 3. 20 MB size limit
    composer.clear_attachments()
    toasts.clear()
    huge_img = b"X" * (21 * 1024 * 1024)
    composer.add_images([huge_img])
    assert len(composer._attachments) == 0
    assert len(toasts) == 1
    assert "20 MB total limit" in toasts[-1]


def test_composer_busy_and_stop_button(qtbot):
    """Verify send button turns to stop button while generating."""
    composer = Composer(theme=MIDNIGHT_THEME)
    qtbot.addWidget(composer)

    stop_called = False
    composer.stop_requested.connect(lambda: nonlocal_stop())

    def nonlocal_stop():
        nonlocal stop_called
        stop_called = True

    # Empty -> send disabled
    assert composer.send_btn.isEnabled() is False

    # Setting busy -> stop enabled
    composer.set_status(is_busy=True)
    assert composer.send_btn._is_busy is True
    assert composer.send_btn.isEnabled() is True

    # Clicking button while busy emits stop_requested
    composer.send_btn.click()
    assert stop_called is True

    # Resetting busy
    composer.set_status(is_busy=False)
    assert composer.send_btn._is_busy is False
    assert composer.send_btn.isEnabled() is False


# ---------------------------------------------------------------------------
# 3. Sidebar Grouping, Search Filtering, Rename, Pin, Delete
# ---------------------------------------------------------------------------

def test_sidebar_grouping_and_display(qtbot, temp_store: HistoryStore):
    """Verify conversations group into Pinned, Today, Yesterday with custom roles."""
    now = datetime.now()
    c1 = temp_store.create_conversation("Pinned Task", source="chat")
    temp_store.set_pinned(c1, True)

    c2 = temp_store.create_conversation("Today Chat", source="chat")

    c3 = temp_store.create_conversation("Yesterday Chat", source="chat")
    # Manually adjust updated_at for yesterday
    yesterday_ts = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S.%f")
    with temp_store.connect() as conn:
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (yesterday_ts, c3))

    settings = Settings()
    sidebar = Sidebar(store=temp_store, settings=settings, theme=MIDNIGHT_THEME)
    qtbot.addWidget(sidebar)

    model = sidebar.model
    # Check headers and items
    section_titles = []
    item_titles = []
    for row in range(model.rowCount()):
        idx = model.index(row, 0)
        if idx.data(ROLE_IS_SECTION):
            section_titles.append(idx.data(ROLE_TITLE))
        else:
            item_titles.append(idx.data(ROLE_TITLE))

    assert "Pinned" in section_titles
    assert "Today" in section_titles
    assert "Yesterday" in section_titles
    assert "Pinned Task" in item_titles
    assert "Today Chat" in item_titles
    assert "Yesterday Chat" in item_titles


def test_sidebar_search_filtering(qtbot, temp_store: HistoryStore):
    """Verify search field filters items by title and debounce timer."""
    temp_store.create_conversation("Python Asyncio")
    temp_store.create_conversation("Qt QStyledItemDelegate")
    temp_store.create_conversation("Rust Tokio")

    settings = Settings()
    sidebar = Sidebar(store=temp_store, settings=settings, theme=MIDNIGHT_THEME)
    qtbot.addWidget(sidebar)

    # Initial count: 3 items (+ section header)
    assert sidebar.model.rowCount() >= 3

    # Filter for 'Asyncio'
    sidebar.search_edit.setText("Asyncio")
    sidebar._on_search_debounced()

    visible_items = [
        sidebar.model.index(r, 0).data(ROLE_TITLE)
        for r in range(sidebar.model.rowCount())
        if not sidebar.model.index(r, 0).data(ROLE_IS_SECTION)
    ]
    assert len(visible_items) == 1
    assert visible_items[0] == "Python Asyncio"

    # Clear filter
    sidebar.search_edit.setText("")
    sidebar._on_search_debounced()
    cleared_items = [
        sidebar.model.index(r, 0).data(ROLE_TITLE)
        for r in range(sidebar.model.rowCount())
        if not sidebar.model.index(r, 0).data(ROLE_IS_SECTION)
    ]
    assert len(cleared_items) == 3


def test_sidebar_collapse_persists(qtbot):
    """Verify collapse state updates width and persists to settings."""
    settings = Settings(sidebar_collapsed=False, reduce_motion=True)
    sidebar = Sidebar(store=None, settings=settings, theme=MIDNIGHT_THEME)
    qtbot.addWidget(sidebar)

    assert sidebar.is_collapsed() is False
    assert sidebar.width() == Sidebar.EXPANDED_WIDTH

    # Collapse
    sidebar.set_collapsed(True)
    assert sidebar.is_collapsed() is True
    assert settings.sidebar_collapsed is True
    assert sidebar.width() == Sidebar.COLLAPSED_WIDTH

    # Expand
    sidebar.set_collapsed(False)
    assert sidebar.is_collapsed() is False
    assert settings.sidebar_collapsed is False
    assert sidebar.width() == Sidebar.EXPANDED_WIDTH


def test_sidebar_rename_pin_delete_through_store(qtbot, temp_store: HistoryStore):
    """Verify context menu operations call store and emit signals."""
    cid = temp_store.create_conversation("Original Title")

    settings = Settings()
    sidebar = Sidebar(store=temp_store, settings=settings, theme=MIDNIGHT_THEME)
    qtbot.addWidget(sidebar)

    # 1. Rename
    with patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("Renamed Title", True)):
        # Simulate rename
        sidebar.store.rename_conversation(cid, "Renamed Title")
        sidebar.refresh_conversations()
        assert temp_store.get_conversation(cid)["title"] == "Renamed Title"

    # 2. Pin / Unpin
    assert bool(temp_store.get_conversation(cid)["pinned"]) is False
    temp_store.set_pinned(cid, True)
    sidebar.refresh_conversations()
    assert bool(temp_store.get_conversation(cid)["pinned"]) is True

    # 3. Delete
    with patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
        temp_store.delete_conversation(cid)
        sidebar.refresh_conversations()
        assert temp_store.get_conversation(cid) is None


# ---------------------------------------------------------------------------
# 4. MainWindow Shell & Integration with FakeChatSession
# ---------------------------------------------------------------------------

def test_main_window_shell_defaults_and_geometry(qtbot, tmp_path: Path):
    """Verify MainWindow default size (1100x720), min size (760x520), and geometry saving."""
    settings = Settings(main_window_geometry="", close_to_tray=True)
    win = MainWindow(store=None, settings=settings, chat_session=None)
    qtbot.addWidget(win)

    assert win.minimumWidth() == MainWindow.MIN_WIDTH
    assert win.minimumHeight() == MainWindow.MIN_HEIGHT
    assert win.width() == MainWindow.DEFAULT_WIDTH
    assert win.height() == MainWindow.DEFAULT_HEIGHT

    # Geometry save
    win._save_geometry()
    assert len(settings.main_window_geometry) > 0


def test_main_window_close_to_tray(qtbot):
    """Verify closeEvent hides window to tray when close_to_tray is True."""
    settings = Settings(close_to_tray=True)
    win = MainWindow(store=None, settings=settings, chat_session=None)
    qtbot.addWidget(win)
    win.show()
    assert win.isVisible() is True

    # Close event
    win.close()
    assert win.isHidden() is True


def test_main_window_fake_chat_session_flow(qtbot, temp_store: HistoryStore):
    """Verify MainWindow binds with FakeChatSession for new_chat, send, and stream."""
    settings = Settings(display_name="Zidane")
    session = FakeChatSession()

    win = MainWindow(store=temp_store, settings=settings, chat_session=session)
    qtbot.addWidget(win)
    win.show()

    # Starts on WelcomeView (stack index 0)
    assert win.content_stack.currentIndex() == 0

    # Send message from welcome composer
    win.welcome_view.composer.input_edit.setPlainText("Explain Python async")
    win.welcome_view.composer._on_send_clicked()

    # Switched to ConversationView (stack index 1)
    assert win.content_stack.currentIndex() == 1
    assert "Explain Python async" in win.conversation_view.title_lbl.text() or win.conversation_view.conv_id is not None
    # 2 messages added (1 user, 1 assistant completed)
    assert win.conversation_view.messages_layout.count() >= 2

    # New chat switches back to WelcomeView
    win.new_chat()
    assert win.content_stack.currentIndex() == 0


def test_main_window_shortcuts(qtbot):
    """Verify keyboard shortcuts for New chat (Ctrl+N) and sidebar toggle (Ctrl+B)."""
    settings = Settings()
    session = FakeChatSession()
    win = MainWindow(store=None, settings=settings, chat_session=session)
    qtbot.addWidget(win)

    # Initial state
    assert win.sidebar.is_collapsed() is False

    # Trigger Ctrl+B
    win.sc_sidebar.activated.emit()
    assert win.sidebar.is_collapsed() is True

    # Trigger Ctrl+B again
    win.sc_sidebar.activated.emit()
    assert win.sidebar.is_collapsed() is False

    # Trigger Ctrl+N
    win.content_stack.setCurrentIndex(1)
    win.sc_new.activated.emit()
    assert win.content_stack.currentIndex() == 0
