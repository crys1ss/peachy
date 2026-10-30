"""Application Controller orchestrating state transitions and component workflows.

Wires:
Global Hotkey / Tray -> Screen Capture -> Overlay -> Popup Views -> Gemini Provider
through the StateManager FSM.
"""

from __future__ import annotations

import atexit
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
from history.store import HistoryStore, create_thumbnail, generate_title
from history.worker import HistoryDbWorker
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
        history_store: Optional[HistoryStore] = None,
        history_window: Optional[Any] = None,
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
        self.history_store = history_store or HistoryStore()
        self.history_window = history_window
        self.overlay_manager.mode = getattr(self.settings, "selection_mode", "freehand")
        self.overlay_manager.outside_shape = getattr(self.settings, "outside_shape", "blank")

        # Request state tracking
        self._current_request_id: int = 0
        self._active_worker: Optional[GeminiWorker] = None
        self._current_image_bytes: Optional[bytes] = None
        self._first_image_bytes: Optional[bytes] = None
        self._first_question: str = ""
        self._current_history: List[Any] = []
        self._current_conversation_id: Optional[int] = None
        self._last_question: str = ""
        self._saved_foreground_hwnd: int = 0
        self._saved_foreground_title: str = ""
        self._is_new_screenshot_flow: bool = False
        self._db_worker: Optional[HistoryDbWorker] = None
        self._debug_crop_paths: List[Path] = []
        atexit.register(self._cleanup_debug_crops)

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
        if hasattr(self.popup, "length_changed"):
            self.popup.length_changed.connect(self._on_length_changed)
        if hasattr(self.popup, "opt_in_choice"):
            self.popup.opt_in_choice.connect(self.on_opt_in_choice)
        if hasattr(self.popup, "history_requested"):
            self.popup.history_requested.connect(self.open_history)

        # History and Tray
        if hasattr(self.tray_manager, "history_requested"):
            self.tray_manager.history_requested.connect(self.open_history)
        if hasattr(self.hotkey_manager, "history_hotkey_triggered"):
            self.hotkey_manager.history_hotkey_triggered.connect(self.open_history)
        if self.history_window and hasattr(self.history_window, "continue_chat_requested"):
            self.history_window.continue_chat_requested.connect(self.continue_conversation)

        # Monitor resolution & multi-screen topology listeners
        q_app = QGuiApplication.instance()
        if q_app:
            q_app.screenAdded.connect(self._on_screen_topology_changed)
            q_app.screenRemoved.connect(self._on_screen_topology_changed)
            for sc in q_app.screens():
                sc.availableGeometryChanged.connect(self._on_screen_topology_changed)

    def _on_length_changed(self, length: str) -> None:
        """Handle length chip toggle ("short" / "detailed")."""
        self.settings.answer_length = length
        logger.info("Answer length mode set to: %s", length)

    def _on_screen_topology_changed(self, *args: Any) -> None:
        """Re-clamp popup position when screens or geometries change."""
        if self.popup.isVisible():
            screen = QGuiApplication.screenAt(self.popup.pos()) or QGuiApplication.primaryScreen()
            if screen:
                ag = screen.availableGeometry()
                from capture.geometry import clamp_popup_to_screen
                cx, cy = clamp_popup_to_screen(
                    self.popup.x(), self.popup.y(), self.popup.width(), self.popup.height(),
                    ag.x(), ag.y(), ag.width(), ag.height()
                )
                self.popup.move(cx, cy)

    def on_activated(self) -> None:
        """Triggered by global hotkey or tray 'Ask Peachy' menu item."""
        # If currently in ERROR state, dismiss the error and reset to IDLE for fresh capture
        if self.state_manager.state == AppState.ERROR:
            logger.info("Auto-resetting from ERROR state to IDLE on hotkey activation.")
            self.on_popup_cancelled()

        if not self.state_manager.can_activate():
            logger.info("Activation ignored: state is %s (must be IDLE)", self.state_manager.state.value)
            return

        # 1. Record foreground HWND and window title to restore focus and provide context
        self._saved_foreground_hwnd = win32.get_foreground_window()
        self._saved_foreground_title = win32.get_window_text(self._saved_foreground_hwnd)
        logger.info(
            "Peachy activated. Saved foreground HWND: %d ('%s')",
            self._saved_foreground_hwnd,
            self._saved_foreground_title,
        )

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
            self.overlay_manager.start_selection(
                monitors,
                self._saved_foreground_hwnd,
                mode=getattr(self.settings, "selection_mode", "freehand"),
                outside_shape=getattr(self.settings, "outside_shape", "blank"),
            )

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
            self._debug_crop_paths.append(crop_path)
            logger.info("Debug crop saved to %s", crop_path)

        # Convert QImage to PNG bytes
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        crop.save(buffer, "PNG")
        self._current_image_bytes = bytes(byte_array.data())

        # Reset conversation history only if this is a fresh capture, not a New Screenshot flow
        if not self._is_new_screenshot_flow:
            self._current_history = []
            self._current_conversation_id = None
            self._first_question = ""
            self._first_image_bytes = self._current_image_bytes
        self._is_new_screenshot_flow = False
        self._last_question = ""

        # Transition SELECTING -> ASKING
        self.state_manager.transition_to(AppState.ASKING)

        # Display popup in Ask view
        pixmap = QPixmap.fromImage(crop)
        self.popup.show_ask(pixmap)

        # Position popup according to settings: "near_selection" vs "last_used"
        pos_pref = getattr(self.settings, "popup_position", "near_selection")
        last_pos = getattr(self, "_last_popup_pos", None)
        if pos_pref == "last_used" and last_pos is not None:
            self.popup.move(last_pos)
            self.popup.clamp_to_current_screen()
        else:
            target_rect = getattr(self.overlay_manager, "last_selection_rect", None)
            target_screen = getattr(self.overlay_manager, "last_screen", None) or QGuiApplication.primaryScreen()
            if target_rect is not None and target_screen is not None:
                self.popup.position_next_to(target_rect, target_screen)
                self._last_popup_pos = self.popup.pos()

    def on_send_question(self, question: str) -> None:
        """User sent question from the Ask view."""
        if self.state_manager.state != AppState.ASKING:
            logger.warning("send_question ignored: state is %s (must be ASKING)", self.state_manager.state.value)
            return

        prompt = question.strip() if question and question.strip() else "Explain this screen"
        if not self._first_question:
            self._first_question = prompt
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
            answer_length=getattr(self.settings, "answer_length", "short"),
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

        # If this was an OCR Copy Text request, automatically copy raw text to clipboard
        if "Extract all visible text in this image verbatim" in self._last_question:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(result.text.strip())
                logger.info("Extracted text automatically copied to clipboard (%d chars)", len(result.text))

        # Transition THINKING -> ANSWERING
        self.state_manager.transition_to(AppState.ANSWERING)
        self.popup.show_answer(result.text, question=self._last_question)
        logger.info("AI request %d answered successfully (%d history turns)", request_id, len(result.history))

        # Check opt-in prompt or save completed answer
        if not getattr(self.settings, "save_history_prompted", False):
            self.popup.show_opt_in_prompt(True)
        else:
            self.popup.show_opt_in_prompt(False)
            if getattr(self.settings, "save_history", False):
                self._save_current_completed_turn(result.text)

    def on_opt_in_choice(self, save_chosen: bool) -> None:
        """Handle user choice from the one-time opt-in banner."""
        from config.settings import save_settings
        self.settings.save_history_prompted = True
        self.settings.save_history = save_chosen
        save_settings(self.settings)
        self.popup.show_opt_in_prompt(False)
        logger.info("User selected history opt-in: save_history=%s", save_chosen)

        if save_chosen and self._current_history:
            last_text = ""
            last_turn = self._current_history[-1]
            if hasattr(last_turn, "parts") and last_turn.parts:
                last_text = getattr(last_turn.parts[0], "text", "")
            elif isinstance(last_turn, dict) and "parts" in last_turn and last_turn["parts"]:
                p = last_turn["parts"][0]
                last_text = p.get("text", "") if isinstance(p, dict) else str(p)
            self._save_current_completed_turn(last_text)

    def _save_current_completed_turn(self, answer_text: str) -> None:
        """Save completed turn off the UI thread via HistoryDbWorker."""
        if not getattr(self.settings, "save_history", False):
            return

        first_q = self._first_question or self._last_question or "Explain this screen"
        first_img = self._first_image_bytes
        curr_q = self._last_question or "Explain this screen"
        curr_img = self._current_image_bytes
        is_new_conv = self._current_conversation_id is None
        conv_id = self._current_conversation_id
        save_thumbs = getattr(self.settings, "save_thumbnails", False)

        def task():
            try:
                from datetime import datetime
                if is_new_conv:
                    title = generate_title(first_q, answer_text)
                    thumbnail = create_thumbnail(first_img) if save_thumbs and first_img else None
                    with self.history_store.connect() as conn:
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                        cur = conn.execute(
                            "INSERT INTO conversations (title, created_at, updated_at, thumbnail) VALUES (?, ?, ?, ?);",
                            (title, now_str, now_str, thumbnail),
                        )
                        new_id = int(cur.lastrowid)
                        self._current_conversation_id = new_id
                        conn.execute(
                            "INSERT INTO messages (conversation_id, role, text, created_at, has_image) VALUES (?, ?, ?, ?, ?);",
                            (new_id, "user", first_q, now_str, int(bool(first_img))),
                        )
                        conn.execute(
                            "INSERT INTO messages (conversation_id, role, text, created_at, has_image) VALUES (?, ?, ?, ?, ?);",
                            (new_id, "model", answer_text, now_str, 0),
                        )
                    logger.info("Saved new conversation %d ('%s') to history.", new_id, title)
                else:
                    with self.history_store.connect() as conn:
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                        conn.execute(
                            "INSERT INTO messages (conversation_id, role, text, created_at, has_image) VALUES (?, ?, ?, ?, ?);",
                            (conv_id, "user", curr_q, now_str, int(bool(curr_img))),
                        )
                        conn.execute(
                            "INSERT INTO messages (conversation_id, role, text, created_at, has_image) VALUES (?, ?, ?, ?, ?);",
                            (conv_id, "model", answer_text, now_str, 0),
                        )
                        conn.execute(
                            "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                            (now_str, conv_id),
                        )
                    logger.info("Appended message to conversation %d in history.", conv_id)
            except Exception as exc:
                logger.warning("Failed to save conversation to history: %s", exc)

        try:
            self._db_worker = HistoryDbWorker(task, parent=self)
            self._db_worker.start()
        except Exception as err:
            logger.warning("Failed to launch history DB worker: %s", err)

    def open_history(self) -> None:
        """Open History window. Allowed in every state except SELECTING."""
        if self.state_manager.state == AppState.SELECTING:
            logger.info("Opening History ignored: state is SELECTING.")
            return

        if hasattr(self, "history_window") and self.history_window:
            self.history_window.refresh_and_show()

    def continue_conversation(self, conversation_id: int) -> None:
        """Load past conversation into popup with last 20 messages for provider follow-up."""
        conv = self.history_store.get_conversation(conversation_id)
        if not conv:
            logger.warning("Conversation %d not found in history store.", conversation_id)
            return

        raw_messages = self.history_store.get_last_messages(conversation_id, limit=20)
        if not raw_messages:
            logger.warning("No messages found for conversation %d.", conversation_id)
            return

        self._current_conversation_id = conversation_id
        self._current_image_bytes = None
        self._first_image_bytes = None
        self._is_new_screenshot_flow = False

        # Format history for provider
        self._current_history = self._format_history_for_provider(raw_messages)

        last_ans = ""
        last_q = ""
        for m in reversed(raw_messages):
            if m["role"] in ("model", "assistant") and not last_ans:
                last_ans = m["text"]
            elif m["role"] == "user" and not last_q:
                last_q = m["text"]

        self._first_question = last_q
        self._last_question = ""

        # Show answer view in popup without stealing focus
        self.popup.show_answer(last_ans or "Continuing conversation...", question=last_q, is_first_answer=False)
        self.popup.show_note("Earlier screenshots are not re-sent.")

        self.state_manager.resume_conversation()

    def _format_history_for_provider(self, raw_messages: List[dict[str, Any]]) -> List[Any]:
        """Convert stored messages to provider-compatible history entries."""
        result = []
        try:
            from google.genai import types
            for m in raw_messages:
                role = "model" if m["role"] in ("model", "assistant") else "user"
                result.append(types.Content(role=role, parts=[types.Part.from_text(text=m["text"])]))
        except Exception:
            for m in raw_messages:
                role = "model" if m["role"] in ("model", "assistant") else "user"
                result.append({"role": role, "parts": [m["text"]], "text": m["text"]})
        return result

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
        """User clicked 'New Screenshot' in the Answer view.

        Preserves conversation history to continue multi-screenshot chat.
        """
        self.popup.hide()
        self._current_image_bytes = None
        self._is_new_screenshot_flow = True
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
        if hasattr(self.popup, "pill"):
            self.popup.pill.hide()
        self._current_image_bytes = None
        self._first_image_bytes = None
        self._first_question = ""
        self._current_history.clear()
        self._current_conversation_id = None
        self._last_question = ""
        self._is_new_screenshot_flow = False

        # 3. Restore foreground focus
        if self._saved_foreground_hwnd:
            win32.set_foreground_window(self._saved_foreground_hwnd)
            self._saved_foreground_hwnd = 0

        # 4. Return FSM to IDLE
        self.state_manager.reset_to_idle()

    def _cleanup_debug_crops(self) -> None:
        """Delete debug crop files on exit to avoid persisting screen captures."""
        for path in self._debug_crop_paths:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
        self._debug_crop_paths.clear()

    def shutdown(self) -> None:
        """Cancel pending tasks, stop active worker threads, and ensure clean shutdown."""
        logger.info("AppController shutting down...")
        self._cleanup_debug_crops()
        self._hard_timeout_timer.stop()
        if self._active_worker:
            self._active_worker.cancel()
            if self._active_worker.isRunning():
                self._active_worker.terminate()
                self._active_worker.wait(500)
            self._active_worker = None
        self.popup.close()
        self.overlay_manager.cleanup()
