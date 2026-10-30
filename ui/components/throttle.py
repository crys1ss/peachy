"""60 ms streaming render throttler for smooth AI token rendering.

Buffers rapid streaming chunks and flushes updates at most once every 60 ms (~16.6 FPS)
to prevent GUI thread saturation and visual stutter.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal


class StreamThrottler(QObject):
    """Throttles incoming text streams to a steady 60 ms cadence."""

    # Emits full accumulated text buffered so far
    throttled_text = Signal(str)

    def __init__(self, interval_ms: int = 60, parent: QObject | None = None):
        super().__init__(parent)
        self.interval_ms = interval_ms
        self._buffer: list[str] = []
        self._dirty = False

        self._timer = QTimer(self)
        self._timer.setInterval(self.interval_ms)
        self._timer.timeout.connect(self._on_tick)

    def append_chunk(self, chunk: str) -> None:
        """Append incoming streaming chunk and start throttle timer if idle."""
        self._buffer.append(chunk)
        self._dirty = True
        if not self._timer.isActive():
            self._timer.start()

    def get_full_text(self) -> str:
        """Return full text accumulated so far."""
        return "".join(self._buffer)

    def _on_tick(self) -> None:
        if self._dirty:
            self._dirty = False
            self.throttled_text.emit(self.get_full_text())

    def flush(self) -> None:
        """Immediately stop timer and emit full accumulated text."""
        if self._timer.isActive():
            self._timer.stop()
        if self._dirty:
            self._dirty = False
            self.throttled_text.emit(self.get_full_text())

    def reset(self) -> None:
        """Reset buffer and stop timer."""
        if self._timer.isActive():
            self._timer.stop()
        self._buffer.clear()
        self._dirty = False

