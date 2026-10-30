"""Integration tests for core/app_controller.py using FakeAIProvider and pytest-qt."""

import time
from typing import Any, List, Optional
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage
import pytest

from ai.provider import AnswerResult, BaseAIProvider, MissingKeyError, TimeoutError
from capture.selection_overlay import OverlayManager
from core.app_controller import AppController
from core.hotkey_manager import HotkeyManager
from core.state_manager import AppState, StateManager
from ui.peachy_popup import PeachyPopup, ViewIndex
from ui.tray_manager import TrayManager


class FakeAIProvider(BaseAIProvider):
    """Controllable test double for BaseAIProvider without network calls."""

    def __init__(self, response_text: str = "Fake response text", delay: float = 0.01):
        self.response_text = response_text
        self.delay = delay
        self.raise_error = None
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

        if self.delay > 0:
            time.sleep(self.delay)

        if self.raise_error:
            raise self.raise_error

        new_history = list(history or [])
        new_history.append({"role": "user", "parts": [question]})
        new_history.append({"role": "model", "parts": [self.response_text]})

        return AnswerResult(text=self.response_text, history=new_history)


@pytest.fixture
def controller_setup(qtbot):
    """Setup full application controller environment."""
    state_mgr = StateManager()
    hotkey_mgr = HotkeyManager()
    tray_mgr = TrayManager()
    overlay_mgr = OverlayManager()
    popup = PeachyPopup()
    provider = FakeAIProvider()

    controller = AppController(
        state_manager=state_mgr,
        hotkey_manager=hotkey_mgr,
        tray_manager=tray_mgr,
        overlay_manager=overlay_mgr,
        popup=popup,
        provider=provider,
    )

    qtbot.addWidget(popup)
    qtbot.addWidget(overlay_mgr)

    yield controller, provider, popup, state_mgr

    controller.on_popup_cancelled()
    tray_mgr.hide()
    overlay_mgr.cleanup()
    hotkey_mgr.cleanup()
    popup.close()


def test_full_happy_path(controller_setup, qtbot):
    """Verify complete end-to-end user flow:

    Activation -> Crop -> Ask view -> Send -> Thinking -> Answer view -> Followup -> Answer -> Cancel -> IDLE
    """
    controller, provider, popup, state_mgr = controller_setup

    assert state_mgr.state == AppState.IDLE

    # 1. Activate (mock win32 and capture_all_monitors)
    from tests.test_selection_overlay import create_mock_monitor
    mock_mon = create_mock_monitor()

    with patch("core.win32.get_foreground_window", return_value=1234), \
         patch("core.app_controller.capture_all_monitors", return_value=[mock_mon]):
        controller.on_activated()

    assert state_mgr.state == AppState.SELECTING

    # 2. Confirm selection crop
    img = QImage(120, 80, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 0, 0))
    controller.overlay_manager.last_selection_rect = QRect(100, 100, 120, 80)

    controller.on_crop_confirmed(img)

    assert state_mgr.state == AppState.ASKING
    assert popup.isVisible()
    assert popup.stack.currentIndex() == ViewIndex.ASK

    # 3. Send question from Ask view
    controller.on_send_question("What is this red rectangle?")

    assert state_mgr.state == AppState.THINKING
    assert popup.stack.currentIndex() == ViewIndex.THINKING

    # Wait for worker response
    qtbot.waitUntil(lambda: state_mgr.state == AppState.ANSWERING, timeout=2000)

    assert popup.stack.currentIndex() == ViewIndex.ANSWER
    assert "Fake response text" in popup.answer_view.browser.toPlainText()
    assert "What is this red rectangle?" in popup.answer_view.question_header.text()
    assert provider.last_image_png is not None
    assert provider.last_question == "What is this red rectangle?"

    # 4. Send follow-up question
    provider.response_text = "Followup answer explanation"
    controller.on_send_followup("Can you explain more?")

    assert state_mgr.state == AppState.THINKING
    assert popup.stack.currentIndex() == ViewIndex.THINKING

    qtbot.waitUntil(lambda: state_mgr.state == AppState.ANSWERING, timeout=2000)

    assert popup.stack.currentIndex() == ViewIndex.ANSWER
    assert "Followup answer explanation" in popup.answer_view.browser.toPlainText()
    # Follow-ups do NOT resend image data
    assert provider.last_image_png is None
    assert provider.last_question == "Can you explain more?"

    # 5. Cancel / Close popup returns to IDLE and restores focus
    with patch("core.win32.set_foreground_window") as mock_set_fg:
        controller.on_popup_cancelled()
        mock_set_fg.assert_called_once_with(1234)

    assert state_mgr.state == AppState.IDLE
    assert not popup.isVisible()


def test_stale_response_dropped(controller_setup, qtbot):
    """Verify that cancelled or superseded worker responses are dropped."""
    controller, provider, popup, state_mgr = controller_setup

    provider.delay = 0.1  # Slow request
    state_mgr.transition_to(AppState.CAPTURING)
    state_mgr.transition_to(AppState.SELECTING)
    state_mgr.transition_to(AppState.ASKING)

    # Launch request 1
    controller.on_send_question("Request 1")
    req1_id = controller._current_request_id

    # User immediately cancels
    controller.on_popup_cancelled()
    assert state_mgr.state == AppState.IDLE

    # Wait for the slow worker 1 to finish
    qtbot.wait(150)

    # State must remain IDLE, request 1 response was dropped
    assert state_mgr.state == AppState.IDLE
    assert not popup.isVisible()


def test_double_send_blocked_while_thinking(controller_setup, qtbot):
    """Verify double-sending while THINKING is rejected."""
    controller, provider, popup, state_mgr = controller_setup
    provider.delay = 0.1

    state_mgr.transition_to(AppState.CAPTURING)
    state_mgr.transition_to(AppState.SELECTING)
    state_mgr.transition_to(AppState.ASKING)

    controller.on_send_question("Initial request")
    assert state_mgr.state == AppState.THINKING
    qtbot.waitUntil(lambda: provider.call_count == 1, timeout=500)

    # Attempt to send another question while still THINKING
    controller.on_send_question("Second request")
    controller.on_send_followup("Third request")

    # Call count must not increment because state is THINKING
    assert provider.call_count == 1
    controller.on_popup_cancelled()


def test_missing_key_shows_error_view(controller_setup, qtbot):
    """Verify MissingKeyError displays friendly error view with message."""
    controller, provider, popup, state_mgr = controller_setup
    provider.raise_error = MissingKeyError()

    state_mgr.transition_to(AppState.CAPTURING)
    state_mgr.transition_to(AppState.SELECTING)
    state_mgr.transition_to(AppState.ASKING)

    controller.on_send_question("Question with missing key")

    qtbot.waitUntil(lambda: state_mgr.state == AppState.ERROR, timeout=2000)
    assert popup.stack.currentIndex() == ViewIndex.ERROR
    assert "Gemini API key is missing" in popup.error_view.error_label.text()
    controller.on_popup_cancelled()


def test_hard_timeout_fires_and_shows_error(controller_setup, qtbot):
    """Verify 45-second hard timeout transitions to ERROR and displays timeout message."""
    controller, provider, popup, state_mgr = controller_setup

    state_mgr.transition_to(AppState.CAPTURING)
    state_mgr.transition_to(AppState.SELECTING)
    state_mgr.transition_to(AppState.ASKING)

    controller.on_send_question("Slow request")
    assert state_mgr.state == AppState.THINKING

    # Manually trigger hard timeout timer
    controller._on_hard_timeout()

    assert state_mgr.state == AppState.ERROR
    assert popup.stack.currentIndex() == ViewIndex.ERROR
    assert "timed out" in popup.error_view.error_label.text()
    controller.on_popup_cancelled()


def test_new_screenshot_preserves_conversation_history(controller_setup, qtbot):
    """Verify 'New Screenshot' keeps previous conversation history while Close resets it."""
    controller, provider, popup, state_mgr = controller_setup
    from tests.test_selection_overlay import create_mock_monitor
    mock_mon = create_mock_monitor()

    # 1. First capture and answer
    with patch("core.win32.get_foreground_window", return_value=100), \
         patch("core.app_controller.capture_all_monitors", return_value=[mock_mon]):
        controller.on_activated()

    img1 = QImage(100, 100, QImage.Format.Format_RGB32)
    controller.on_crop_confirmed(img1)
    controller.on_send_question("First question")
    qtbot.waitUntil(lambda: state_mgr.state == AppState.ANSWERING, timeout=2000)

    assert len(controller._current_history) == 2

    # 2. Click 'New Screenshot'
    with patch("core.win32.get_foreground_window", return_value=100), \
         patch("core.app_controller.capture_all_monitors", return_value=[mock_mon]):
        controller.on_new_screenshot()

    assert state_mgr.state == AppState.SELECTING
    # History must be preserved!
    assert len(controller._current_history) == 2

    # 3. Confirm second crop
    img2 = QImage(120, 120, QImage.Format.Format_RGB32)
    controller.on_crop_confirmed(img2)
    assert len(controller._current_history) == 2

    # 4. Cancel / Close resets history
    controller.on_popup_cancelled()
    assert len(controller._current_history) == 0
    assert state_mgr.state == AppState.IDLE


def test_hotkey_pressed_during_selecting_is_ignored(controller_setup, qtbot):
    """Verify hotkey activation while in SELECTING state is safely ignored and does not double-activate."""
    controller, provider, popup, state_mgr = controller_setup
    from tests.test_selection_overlay import create_mock_monitor
    mock_mon = create_mock_monitor()

    # Move to SELECTING
    with patch("core.win32.get_foreground_window", return_value=123), \
         patch("core.app_controller.capture_all_monitors", return_value=[mock_mon]):
        controller.on_activated()

    assert state_mgr.state == AppState.SELECTING

    # Press hotkey again while SELECTING
    with patch("core.app_controller.capture_all_monitors") as mock_capture:
        controller.on_activated()
        # Must not re-trigger capture
        mock_capture.assert_not_called()

    # State remains in SELECTING
    assert state_mgr.state == AppState.SELECTING

    controller.on_overlay_cancelled()
    assert state_mgr.state == AppState.IDLE


def test_copy_text_auto_clipboard_copy(controller_setup, qtbot):
    """Verify Copy Text requests automatically copy raw extracted text to system clipboard."""
    controller, provider, popup, state_mgr = controller_setup
    from PySide6.QtGui import QGuiApplication

    provider.response_text = "RAW EXTRACTED OCR TEXT FROM SCREEN"

    state_mgr.transition_to(AppState.CAPTURING)
    state_mgr.transition_to(AppState.SELECTING)

    dummy_image = QImage(100, 50, QImage.Format.Format_RGB32)
    controller.on_crop_confirmed(dummy_image)
    assert state_mgr.state == AppState.ASKING

    ocr_prompt = "Extract all visible text in this image verbatim. Do not add preamble, explanations, or commentary. Output raw text only."
    controller.on_send_question(ocr_prompt)

    qtbot.waitUntil(lambda: state_mgr.state == AppState.ANSWERING, timeout=2000)

    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    assert clipboard.text() == "RAW EXTRACTED OCR TEXT FROM SCREEN"
    assert popup.answer_view.header_title.text() == "Extracted Text (Copied to Clipboard)"


def test_hotkey_while_in_error_state_auto_resets_and_activates(controller_setup, qtbot):
    """Verify pressing the hotkey while in ERROR state auto-dismisses error and starts fresh capture."""
    controller, provider, popup, state_mgr = controller_setup
    from tests.test_selection_overlay import create_mock_monitor
    mock_mon = create_mock_monitor()

    # Move to ERROR state
    state_mgr.transition_to(AppState.CAPTURING)
    state_mgr.transition_to(AppState.SELECTING)
    state_mgr.transition_to(AppState.ASKING)
    state_mgr.transition_to(AppState.THINKING)
    state_mgr.transition_to(AppState.ERROR)
    popup.show_error("Test error message")
    assert state_mgr.state == AppState.ERROR

    # Trigger activation via hotkey
    with patch("core.win32.get_foreground_window", return_value=123), \
         patch("core.app_controller.capture_all_monitors", return_value=[mock_mon]):
        controller.on_activated()

    # Must transition out of ERROR to SELECTING for fresh capture
    assert state_mgr.state == AppState.SELECTING
    controller.on_overlay_cancelled()
    assert state_mgr.state == AppState.IDLE



def test_app_controller_sound_manager_startup_and_save_exchange(tmp_path, qtbot):
    """AppController initializes sound_manager with settings and delegates _save_to_history to save_exchange."""
    from unittest.mock import MagicMock
    from config.settings import Settings
    from core.state_manager import StateManager
    from core.hotkey_manager import HotkeyManager
    from capture.selection_overlay import OverlayManager
    from ui.tray_manager import TrayManager
    from ui.peachy_popup import PeachyPopup
    from history.store import HistoryStore
    from core.app_controller import AppController

    settings = Settings(sound_enabled=True, sound_volume=65, save_history=True)
    store = HistoryStore(db_path=tmp_path / "ctrl_test.db")
    state_mgr = StateManager()
    hotkey_mgr = HotkeyManager()
    tray_mgr = TrayManager()
    overlay_mgr = OverlayManager()
    popup = PeachyPopup()

    controller = AppController(
        state_manager=state_mgr,
        hotkey_manager=hotkey_mgr,
        tray_manager=tray_mgr,
        overlay_manager=overlay_mgr,
        popup=popup,
        settings=settings,
        history_store=store,
    )
    qtbot.addWidget(popup)

    # 1. Verify sound_manager initialized at startup
    assert hasattr(controller, "sound_manager")
    assert controller.sound_manager is not None
    assert controller.sound_manager.get_volume() == 65

    # 2. Verify _save_to_history delegates to HistoryStore.save_exchange
    store.save_exchange = MagicMock(return_value=42)
    controller._first_question = "Test First Question"
    controller._save_to_history("Test Answer")

    # Wait for background worker to execute
    qtbot.waitUntil(lambda: store.save_exchange.called, timeout=2000)
    store.save_exchange.assert_called_once()
    call_kwargs = store.save_exchange.call_args.kwargs
    assert call_kwargs["question"] == "Test First Question"
    assert call_kwargs["answer"] == "Test Answer"

    popup.close()
    controller.shutdown()
