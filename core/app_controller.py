"""Application Controller orchestrating state transitions and component workflows.

Wires:
Global Hotkey / Tray -> Screen Capture -> Overlay -> Popup Views -> Gemini Provider
through the StateManager FSM.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import tempfile
import time
from typing import Any, List, Optional

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QRect, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPixmap, QScreen

from ai.gemini_provider import GeminiProvider
from ai.provider import AnswerResult, BaseAIProvider, ProviderError, TimeoutError
from capture.screen_capture import capture_all_monitors
from capture.selection_overlay import OverlayManager
from config.settings import Settings, load_settings
from core import win32
from core.hotkey_manager import HotkeyManager
from core.state_manager import AppState, StateManager
from core.worker import GeminiWorker
from ui.peachy_popup import PeachyPopup
from ui.tray_manager import TrayManager

logger = logging.getLogger(__name__)

HARD_TIMEOUT_MS = 45000  # 45 second hard safety timeout


class AppController(QObject):
    """Central coordinator for the Peachy desktop screen assistant."""

    def __init__(
        self,
        state_manager: StateManager,
        hotkey_manager: HotkeyManager,
        tray_manager: TrayManager,
        overlay_manager: OverlayManager,
        popup: PeachyPopup,
        provider: Optional[BaseAIProvider] = None,
        settings: Optional[Settings] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.state_manager = state_manager
        self.hotkey_manager = hotkey_manager
        self.tray_manager = tray_manager
        self.overlay_manager = overlay_manager
        self.popup = popup
        self.provider = provider or GeminiProvider()
        self.settings = settings or load_settings()

        # Request state tracking
        self._current_request_id: int = 0
        self._active_worker: Optional[GeminiWorker] = None
        self._current_image_bytes: Optional[bytes] = None
        self._current_history: List[Any] = []
        self._last_question: str = ""
        self._saved_foreground_hwnd: int = 0

        # Hard timeout timer (45s)
        self._hard_timeout_timer = QTimer(self)
        self._hard_timeout_timer.setSingleShot(True)
        self._hard_timeout_timer.timeout.connect(self._on_hard_timeout)

        self._connect_signals()

    def _connect_signals(self) -> None:
        """Wire UI, Hotkey, Overlay, and Popup signals to controller actions."""
        # Hotkey & Tray
        self.hotkey_manager.hotkey_triggered.connect(self.on_activated)
        self.tray_manager.ask_requested.connect(self.on_activated)

        # Overlay selection
        self.overlay_manager.crop_confirmed.connect(self.on_crop_confirmed)
        self.overlay_manager.cancelled.connect(self.on_overlay_cancelled)

        # Popup actions
        self.popup.send_question.connect(self.on_send_question)
        self.popup.send_followup.connect(self.on_send_followup)
        self.popup.retry_requested.connect(self.on_retry)
        self.popup.new_screenshot_requested.connect(self.on_new_screenshot)
        self.popup.cancelled.connect(self.on_popup_cancelled)

    def on_activated(self) -> None:
        """Triggered by global hotkey or tray 'Ask Peachy' menu item."""
        if not self.state_manager.can_activate():
            logger.info("Activation ignored: state is %s (must be IDLE)", self.state_manager.state.value)
            return

        # 1. Record foreground HWND to restore focus when finished
        self._saved_foreground_hwnd = win32.get_foreground_window()
        logger.info("Peachy activated. Saved foreground HWND: %d", self._saved_foreground_hwnd)

        # 2. Transition IDLE -> CAPTURING
        if not self.state_manager.request_activation():
            return

        # 3. Synchronously capture all monitors before any Peachy window appears
        try:
            monitors = capture_all_monitors()
            if not monitors:
                raise RuntimeError("No screens detected by screen capture.")

            # 4. Transition CAPTURING -> SELECTING
            self.state_manager.transition_to(AppState.SELECTING)

            # 5. Display frozen selection overlays
            self.overlay_manager.start_selection(monitors, self._saved_foreground_hwnd)

        except Exception as err:
            logger.exception("Screen capture failed: %s", err)
            self.overlay_manager.cleanup()
            if self._saved_foreground_hwnd:
                win32.set_foreground_window(self._saved_foreground_hwnd)
                self._saved_foreground_hwnd = 0
            self.state_manager.reset_to_idle()

    def on_overlay_cancelled(self) -> None:
        """User cancelled overlay selection (Esc, Right-Click, or 60s timeout)."""
        logger.info("Overlay selection cancelled. Returning to IDLE.")
        self._saved_foreground_hwnd = 0
        self.state_manager.transition_to(AppState.IDLE)

    def on_crop_confirmed(self, crop: QImage) -> None:
        """User completed a valid rectangle selection."""
        logger.info("Selection confirmed: %d x %d physical px", crop.width(), crop.height())

        # Debug switch: if PEACHY_DEBUG_SAVE_CROP=1, write crop PNG to temp directory
        if os.environ.get("PEACHY_DEBUG_SAVE_CROP") == "1":
            temp_dir = Path(tempfile.gettempdir()) / "peachy_crops"
            temp_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            crop_path = temp_dir / f"crop_{timestamp}.png"
            crop.save(str(crop_path), "PNG")
            logger.info("Debug crop saved to %s", crop_path)

        # Convert QImage to PNG bytes
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        crop.save(buffer, "PNG")
        self._current_image_bytes = bytes(byte_array.data())

        # Reset conversation history for new screenshot
        self._current_history = []
        self._last_question = ""

        # Transition SELECTING -> ASKING
        self.state_manager.transition_to(AppState.ASKING)

        # Display popup in Ask view
        pixmap = QPixmap.fromImage(crop)
        self.popup.show_ask(pixmap)

        # Position popup adjacent to selection
        target_rect = getattr(self.overlay_manager, "last_selection_rect", None)
        target_screen = getattr(self.overlay_manager, "last_screen", None) or QGuiApplication.primaryScreen()
        if target_rect is not None and target_screen is not None:
            self.popup.position_next_to(target_rect, target_screen)

    def on_send_question(self, question: str) -> None:
        """User sent question from the Ask view."""
        if self.state_manager.state != AppState.ASKING:
            logger.warning("send_question ignored: state is %s (must be ASKING)", self.state_manager.state.value)
            return

        prompt = question.strip() if question and question.strip() else "Explain this screen"
        self._start_ai_request(question=prompt, image_png=self._current_image_bytes, is_followup=False)

    def on_send_followup(self, question: str) -> None:
        """User sent follow-up question from the Answer view."""
        if self.state_manager.state != AppState.ANSWERING:
            logger.warning("send_followup ignored: state is %s (must be ANSWERING)", self.state_manager.state.value)
            return

        # Follow-ups do not resend image bytes; they carry conversation history
        self._start_ai_request(question=question, image_png=None, is_followup=True)

    def on_retry(self) -> None:
        """User clicked Retry in the Error view."""
        if self.state_manager.state != AppState.ERROR:
            logger.warning("retry ignored: state is %s (must be ERROR)", self.state_manager.state.value)
            return

        # Re-send last question
        img_bytes = self._current_image_bytes if not self._current_history else None
        self._start_ai_request(question=self._last_question, image_png=img_bytes, is_followup=bool(self._current_history))

    def _start_ai_request(self, question: str, image_png: Optional[bytes], is_followup: bool) -> None:
        """Orchestrate worker dispatch into THINKING state."""
        # 1. State transition to THINKING
        if not self.state_manager.transition_to(AppState.THINKING):
            logger.warning("Cannot transition to THINKING from %s", self.state_manager.state.value)
            return

        self.popup.show_thinking()

        # 2. Cancel any existing worker and tag new request ID
        if self._active_worker:
            self._active_worker.cancel()
            if self._active_worker.isRunning():
                self._active_worker.wait(500)
            self._active_worker = None

        self._current_request_id += 1
        req_id = self._current_request_id
        self._last_question = question

        # 3. Create worker
        self._active_worker = GeminiWorker(
            provider=self.provider,
            request_id=req_id,
            image_png=image_png,
            question=question,
            history=self._current_history,
            parent=self,
        )
        self._active_worker.result_ready.connect(self._on_worker_result)
        self._active_worker.error_occurred.connect(self._on_worker_error)

        # 4. Start hard timeout timer (45s)
        self._hard_timeout_timer.start(HARD_TIMEOUT_MS)

        # 5. Launch thread
        self._active_worker.start()
        logger.info("Dispatched AI request %d (question='%s', has_image=%s)", req_id, question, bool(image_png))

    def _on_worker_result(self, request_id: int, result: AnswerResult) -> None:
        """Handle successful response from worker."""
        if request_id != self._current_request_id:
            logger.info("Dropping stale worker result %d (current is %d)", request_id, self._current_request_id)
            return

        self._hard_timeout_timer.stop()
        if self._active_worker and self._active_worker.isRunning():
            self._active_worker.wait(1000)
        self._active_worker = None

        # Update conversation history
        self._current_history = result.history

        # Transition THINKING -> ANSWERING
        self.state_manager.transition_to(AppState.ANSWERING)
        self.popup.show_answer(result.text, question=self._last_question)
        logger.info("AI request %d answered successfully (%d history turns)", request_id, len(result.history))

    def _on_worker_error(self, request_id: int, error: ProviderError) -> None:
        """Handle error from worker."""
        if request_id != self._current_request_id:
            logger.info("Dropping stale worker error %d (current is %d)", request_id, self._current_request_id)
            return

        self._hard_timeout_timer.stop()
        if self._active_worker and self._active_worker.isRunning():
            self._active_worker.wait(1000)
        self._active_worker = None

        # Transition THINKING -> ERROR
        self.state_manager.transition_to(AppState.ERROR)
        self.popup.show_error(error.message)
        logger.warning("AI request %d failed: %s (%s)", request_id, type(error).__name__, error.message)

    def _on_hard_timeout(self) -> None:
        """Handle 45-second hard timeout expiry."""
        if self.state_manager.state != AppState.THINKING:
            return

        logger.error("Request %d exceeded hard timeout of 45s.", self._current_request_id)
        if self._active_worker:
            self._active_worker.cancel()
            if self._active_worker.isRunning():
                self._active_worker.wait(1000)
            self._active_worker = None

        self._current_request_id += 1
        self.state_manager.transition_to(AppState.ERROR)
        self.popup.show_error(TimeoutError.DEFAULT_MESSAGE)

    def on_new_screenshot(self) -> None:
        """User clicked 'New Screenshot' in the Answer view."""
        self.popup.hide()
        self._current_image_bytes = None
        self._current_history = []
        self._last_question = ""

        # Transition ANSWERING -> IDLE -> CAPTURING
        self.state_manager.transition_to(AppState.IDLE)
        self.on_activated()

    def on_popup_cancelled(self) -> None:
        """User closed or cancelled the popup window."""
        logger.info("Popup closed by user. Cleaning up and returning to IDLE.")

        # 1. Mark active worker cancelled immediately
        if self._active_worker:
            self._active_worker.cancel()
            if self._active_worker.isRunning():
                self._active_worker.wait(1000)
            self._active_worker = None

        self._hard_timeout_timer.stop()
        self._current_request_id += 1  # Invalidate pending responses

        # 2. Hide popup and free resources
        self.popup.hide()
        self._current_image_bytes = None
        self._current_history.clear()
        self._last_question = ""

        # 3. Restore foreground focus
        if self._saved_foreground_hwnd:
            win32.set_foreground_window(self._saved_foreground_hwnd)
            self._saved_foreground_hwnd = 0

        # 4. Return FSM to IDLE
        self.state_manager.reset_to_idle()
