"""Motion and animation utilities for Peachy.

Strictly follows docs/REDESIGN.md Section 5:
- Centralized animation orchestration via should_animate, duration, fade, and slide.
- Respects settings.reduce_motion and Windows OS animation effects (SPI_GETCLIENTAREAANIMATION).
- All graphics effects are removed when animations conclude to prevent frame rate degradation.
- When motion is disabled, duration snaps to 0 ms and UI updates instantly.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Union

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from core.win32 import get_client_area_animation_enabled

logger = logging.getLogger(__name__)

# Standard duration constants (REDESIGN.md section 5)
DUR_LAUNCH = 220
DUR_WELCOME = 260
DUR_SIDEBAR = 200
DUR_CHAT_SWITCH = 140
DUR_MESSAGE_ENTER = 180
DUR_HOVER = 120
DUR_PRESS = 80
DUR_FOCUS_GLOW = 160
DUR_DROPDOWN = 140
DUR_SETTINGS = 200
DUR_PALETTE = 160
DUR_TOAST_IN = 180
DUR_TOAST_OUT = 140
DUR_SMOOTH_SCROLL = 200


def should_animate(settings: Optional[Any] = None) -> bool:
    """Return True if UI animations should run, False if motion reduction is requested.

    Checks both the application settings.reduce_motion and the Windows OS
    SystemParametersInfo client area animation setting.
    """
    if settings is not None and getattr(settings, "reduce_motion", False):
        return False
    return get_client_area_animation_enabled()


def duration(ms: int, settings: Optional[Any] = None) -> int:
    """Return effective animation duration in milliseconds.

    Returns 0 when should_animate() is False.
    """
    if not should_animate(settings):
        return 0
    return max(0, int(ms))


def fade(
    widget: QWidget,
    start: float,
    end: float,
    ms: int,
    curve: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
    on_finished: Optional[Callable[[], None]] = None,
    settings: Optional[Any] = None,
) -> Optional[QPropertyAnimation]:
    """Animate widget opacity using QGraphicsOpacityEffect.

    Removes the opacity effect upon completion if final opacity is >= 1.0.
    Snaps instantly without animation when duration is 0 ms.
    """
    if widget is None:
        return None

    eff_ms = duration(ms, settings)
    if eff_ms == 0:
        if end >= 1.0:
            widget.setGraphicsEffect(None)
        else:
            effect = widget.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(widget)
                widget.setGraphicsEffect(effect)
            effect.setOpacity(end)
        if on_finished is not None:
            on_finished()
        return None

    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(start)

    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(eff_ms)
    anim.setStartValue(float(start))
    anim.setEndValue(float(end))
    anim.setEasingCurve(curve)

    def _on_done() -> None:
        if end >= 1.0:
            widget.setGraphicsEffect(None)
        if on_finished is not None:
            on_finished()

    anim.finished.connect(_on_done)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def slide(
    widget: QWidget,
    prop: Union[bytes, str],
    start: Any,
    end: Any,
    ms: int,
    curve: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
    on_finished: Optional[Callable[[], None]] = None,
    settings: Optional[Any] = None,
) -> Optional[QPropertyAnimation]:
    """Animate a widget property (e.g. pos, geometry, maximumWidth).

    Snaps instantly when duration is 0 ms.
    """
    if widget is None:
        return None

    eff_ms = duration(ms, settings)
    prop_bytes = prop.encode("utf-8") if isinstance(prop, str) else prop

    if eff_ms == 0:
        if prop_bytes == b"pos" and isinstance(end, QPoint):
            widget.move(end)
        elif prop_bytes == b"geometry" and isinstance(end, QRect):
            widget.setGeometry(end)
        elif prop_bytes == b"maximumWidth" and isinstance(end, int):
            widget.setMaximumWidth(end)
        elif prop_bytes == b"maximumHeight" and isinstance(end, int):
            widget.setMaximumHeight(end)
        else:
            widget.setProperty(prop_bytes.decode("utf-8"), end)
        if on_finished is not None:
            on_finished()
        return None

    anim = QPropertyAnimation(widget, prop_bytes, widget)
    anim.setDuration(eff_ms)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(curve)
    if on_finished is not None:
        anim.finished.connect(on_finished)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim
