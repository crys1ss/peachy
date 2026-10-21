"""Asynchronous QThread worker for executing AI provider requests off the UI thread.

Features:
- Unique request ID tagging to prevent stale responses from updating UI.
- Cancellation support that immediately marks requests obsolete.
- Strict mapping of results and typed ProviderErrors to Qt signals.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from PySide6.QtCore import QThread, Signal

from ai.provider import AnswerResult, BaseAIProvider, ProviderError, UnknownError

logger = logging.getLogger(__name__)


class GeminiWorker(QThread):
    """Worker thread executing Gemini API calls."""

    result_ready = Signal(int, AnswerResult)       # request_id, result
    error_occurred = Signal(int, ProviderError)    # request_id, error

    def __init__(
        self,
        provider: BaseAIProvider,
        request_id: int,
        image_png: Optional[bytes],
        question: str,
        history: Optional[List[Any]] = None,
        parent: Optional[Any] = None,
    ):
        super().__init__(parent)
        self.provider = provider
        self.request_id = request_id
        self.image_png = image_png
        self.question = question
        self.history = history or []
        self._is_cancelled = False

    def cancel(self) -> None:
        """Mark this worker request as cancelled/obsolete."""
        self._is_cancelled = True
        logger.debug("Worker request %d marked as cancelled.", self.request_id)

    @property
    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def run(self) -> None:
        """Execute the AI provider request off the main GUI thread."""
        logger.debug("Worker starting request %d...", self.request_id)
        try:
            result = self.provider.ask(
                image_png=self.image_png,
                question=self.question,
                history=self.history,
            )

            if not self._is_cancelled:
                logger.debug("Worker request %d succeeded.", self.request_id)
                self.result_ready.emit(self.request_id, result)
            else:
                logger.info("Worker request %d completed but dropped because cancelled.", self.request_id)

        except ProviderError as err:
            if not self._is_cancelled:
                logger.warning("Worker request %d failed with %s: %s", self.request_id, type(err).__name__, err.message)
                self.error_occurred.emit(self.request_id, err)
            else:
                logger.info("Worker request %d failed but dropped because cancelled.", self.request_id)

        except Exception as err:
            if not self._is_cancelled:
                logger.exception("Worker request %d encountered unhandled exception: %s", self.request_id, err)
                self.error_occurred.emit(self.request_id, UnknownError(str(err), err))
            else:
                logger.info("Worker request %d errored but dropped because cancelled.", self.request_id)
