"""Asynchronous QThread worker for executing database write operations off the UI thread."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)


class HistoryDbWorker(QThread):
    """Executes SQLite writes asynchronously to prevent UI thread blocking."""

    finished = Signal(object)
    failed = Signal(Exception)

    def __init__(self, task: Callable[..., Any], *args: Any, parent: Optional[QObject] = None, **kwargs: Any):
        super().__init__(parent)
        self.task = task
        self.args = args
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            result = self.task(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as exc:
            logger.exception("HistoryDbWorker encountered error: %s", exc)
            self.failed.emit(exc)
