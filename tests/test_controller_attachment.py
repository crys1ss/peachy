"""Tests for AppController attachment capture mode and main window signals."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QImage

from capture.selection_overlay import OverlayManager
from config.settings import Settings
from core.app_controller import AppController
from core.hotkey_manager import HotkeyManager
from core.state_manager import AppState, StateManager
from history.store import HistoryStore
from tests.fakes.fake_provider import FakeProvider
from ui.peachy_popup import PeachyPopup
from ui.tray_manager import TrayManager


@pytest.fixture
def controller_components(tmp_path):
    """Instantiate AppController and dependencies in test harness."""
    state_mgr = StateManager()
    hotkey_mgr = HotkeyManager()
    tray_mgr = TrayManager()
    overlay_mgr = OverlayManager()
    popup = PeachyPopup()
    provider = FakeProvider()
    settings = Settings()
    history_store = HistoryStore(db_path=tmp_path / "controller_test.db")

    controller = AppController(
        state_manager=state_mgr,
        hotkey_manager=hotkey_mgr,
        tray_manager=tray_mgr,
        overlay_manager=overlay_mgr,
        popup=popup,
        provider=provider,
        settings=settings,
        history_store=history_store,
    )
    return controller, state_mgr, overlay_mgr, popup


def test_capture_for_attachment_flow(controller_components, qtbot):
    """capture_for_attachment activates capture and emits attachment_captured on crop confirmation."""
    controller, state_mgr, overlay_mgr, popup = controller_components

    captured_bytes = []
    controller.attachment_captured.connect(lambda b: captured_bytes.append(b))

    with patch("core.app_controller.capture_all_monitors") as mock_cap:
        mock_cap.return_value = [MagicMock()]
        with patch.object(overlay_mgr, "start_selection"):
            controller.capture_for_attachment()
            assert controller._capturing_for_attachment is True
            assert state_mgr.state == AppState.SELECTING

            # Simulate user confirming a crop
            test_crop = QImage(200, 150, QImage.Format.Format_RGB32)
            controller.on_crop_confirmed(test_crop)

            # Should transition back to IDLE and emit attachment_captured without opening popup
            assert len(captured_bytes) == 1
            assert len(captured_bytes[0]) > 0
            assert controller._capturing_for_attachment is False
            assert state_mgr.state == AppState.IDLE
            assert not popup.isVisible()


def test_capture_for_attachment_cancellation(controller_components):
    """Cancelling overlay during attachment capture mode resets to IDLE cleanly."""
    controller, state_mgr, overlay_mgr, popup = controller_components

    controller._capturing_for_attachment = True
    controller.on_overlay_cancelled()

    assert controller._capturing_for_attachment is False
    assert state_mgr.state == AppState.IDLE


def test_open_in_main_window_signal(controller_components):
    """open_in_main_window signal forwards conversation id."""
    controller, state_mgr, overlay_mgr, popup = controller_components

    emitted = []
    controller.open_in_main_window.connect(lambda cid: emitted.append(cid))

    controller.open_in_main_window.emit(42)
    assert emitted == [42]
