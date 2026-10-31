"""Background QThread worker running provider streaming queries with timeout and cancellation."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, List, Optional

from PySide6.QtCore import QObject, QThread, Signal

from ai.provider import (
    BaseAIProvider,
    BlockedError,
    EmptyResponseError,
    InvalidKeyError,
    MissingKeyError,
    NetworkError,
    RateLimitedError,
    TimeoutError,
    UnknownError,
)

logger = logging.getLogger(__name__)


class StreamWorker(QThread):
    """Executes ask_stream off the UI thread with per-chunk timeout and request tracking."""

    chunk = Signal(int, str)                # request_id, full_text_so_far
    finished = Signal(int, str, dict)       # request_id, full_text, usage_metadata
    failed = Signal(int, str, str, str)     # request_id, error_kind, friendly_message, partial_text

    def __init__(
        self,
        provider: BaseAIProvider,
        request_id: int,
        question: str = "",
        images: list[bytes] = (),
        history: Optional[List[Any]] = None,
        answer_length: str = "short",
        system_instruction: Optional[str] = None,
        timeout_seconds: float = 20.0,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.provider = provider
        self.request_id = request_id
        self.question = question
        self.images = list(images)
        self.history = list(history or [])
        self.answer_length = answer_length
        self.system_instruction = system_instruction
        self.timeout_seconds = timeout_seconds

        self._cancelled = False
        self._full_text = ""
        self._lock = threading.Lock()

    def cancel(self) -> None:
        """Request cancellation of active stream."""
        with self._lock:
            self._cancelled = True

    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def get_full_text(self) -> str:
        with self._lock:
            return self._full_text

    @staticmethod
    def classify_error(exc: Exception) -> tuple[str, str]:
        """Classify an exception into a standard error kind and user-friendly message."""
        if isinstance(exc, MissingKeyError):
            return "no_key", "Add API key in Settings"
        if isinstance(exc, InvalidKeyError):
            return "invalid_key", "Gemini API key is invalid or unauthorized. Please verify your key."
        if isinstance(exc, RateLimitedError):
            return "rate_limited", "Peachy needs a breather, try again in a moment"
        if isinstance(exc, BlockedError):
            return "blocked", "Content was blocked by safety filters. Please try a different question."
        if isinstance(exc, TimeoutError):
            return "offline", "Request to Gemini timed out. Please check your network connection and retry."
        if isinstance(exc, NetworkError):
            return "offline", "You appear to be offline. Please check your internet connection and retry."
        if isinstance(exc, EmptyResponseError):
            return "empty", "Gemini returned an empty response. Try rephrasing your question."
        return "unknown", "An unexpected error occurred while communicating with Gemini."

    def run(self) -> None:
        """Run the streaming query off the UI thread, enforcing per-chunk timeout."""
        request_id = self.request_id
        logger.info("StreamWorker starting request %d", request_id)

        full_text = ""
        usage_info: dict[str, int] = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        # Queue for cross-thread chunk delivery from producer
        q: queue.Queue = queue.Queue()
        sentinel = object()

        def producer() -> None:
            try:
                gen = self.provider.ask_stream(
                    images=self.images,
                    question=self.question,
                    history=self.history,
                    answer_length=self.answer_length,
                )
                for item in gen:
                    if self.is_cancelled():
                        break
                    q.put((True, item))

                # After generator completes, get final usage metadata
                usage = getattr(self.provider, "last_usage_metadata", None)
                q.put((sentinel, usage))
            except Exception as exc:
                q.put((False, exc))

        prod_thread = threading.Thread(target=producer, daemon=True)
        prod_thread.start()

        while True:
            if self.is_cancelled():
                logger.info("StreamWorker request %d cancelled by user", request_id)
                return

            try:
                status, val = q.get(timeout=self.timeout_seconds)
            except queue.Empty:
                if self.is_cancelled():
                    return
                logger.warning("StreamWorker request %d timed out (no chunk for %d s)", request_id, int(self.timeout_seconds))
                self.failed.emit(
                    request_id,
                    "offline",
                    f"No response data received for {int(self.timeout_seconds)} seconds. Please retry.",
                    full_text,
                )
                return

            if status is sentinel:
                if isinstance(val, dict):
                    usage_info = val
                break

            if not status:
                exc = val
                error_kind, friendly_msg = self.classify_error(exc)
                logger.warning("StreamWorker request %d failed: %s (%s)", request_id, error_kind, exc)
                self.failed.emit(request_id, error_kind, friendly_msg, full_text)
                return

            # A text chunk
            chunk_str = str(val)
            full_text += chunk_str
            with self._lock:
                self._full_text = full_text

            self.chunk.emit(request_id, full_text)

        if self.is_cancelled():
            logger.info("StreamWorker request %d cancelled before emitting finish", request_id)
            return

        logger.info("StreamWorker request %d finished successfully (%d chars received)", request_id, len(full_text))
        self.finished.emit(request_id, full_text, usage_info)
