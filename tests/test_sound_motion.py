"""Unit tests for sound effects and Windows motion reduction checking."""

import pytest

from config.settings import Settings
from core.win32 import get_client_area_animation_enabled
from ui.peachy_popup import should_animate
from ui.sound import SoundManager, get_sound_manager


def test_sound_manager_mute_and_volume(qapp):
    """Verify SoundManager volume scaling, mute state, and bidirectional settings sync."""
    settings = Settings(sound_enabled=True, sound_volume=40)
    mgr = SoundManager(settings=settings)

    assert mgr.get_volume() == 40
    assert not mgr.is_muted

    # Set volume
    mgr.set_volume(80)
    assert mgr.get_volume() == 80
    assert settings.sound_volume == 80

    # Volume bounds clamping
    mgr.set_volume(150)
    assert mgr.get_volume() == 100
    mgr.set_volume(-20)
    assert mgr.get_volume() == 0

    # Mute toggle
    mgr.set_muted(True)
    assert mgr.is_muted
    assert not settings.sound_enabled

    # Play when muted returns False
    assert mgr.play("open") is False


def test_sound_manager_rate_limiting(qapp):
    """Verify SoundManager rate limits calls within 150 ms window."""
    settings = Settings(sound_enabled=True, sound_volume=50)
    mgr = SoundManager(settings=settings)

    # First trigger (whether winsound or QSoundEffect available)
    # Even if audio device is absent or mock, timestamp is recorded
    mgr.play("open")

    # Immediate second trigger must be suppressed by 150 ms rate limit
    assert mgr.play("open") is False


def test_motion_reduction_check():
    """Verify should_animate respects settings.reduce_motion and Win32 animations."""
    # When reduce_motion is True, should_animate is strictly False
    s_reduce = Settings(reduce_motion=True)
    assert should_animate(s_reduce) is False

    # When reduce_motion is False, should_animate queries OS setting
    s_normal = Settings(reduce_motion=False)
    os_anim = get_client_area_animation_enabled()
    assert should_animate(s_normal) == os_anim



def test_sound_manager_rereads_updated_settings(qapp):
    """get_sound_manager(new_settings) re-reads sound_enabled and sound_volume live."""
    s1 = Settings(sound_enabled=True, sound_volume=25)
    mgr1 = get_sound_manager(s1)
    assert mgr1.get_volume() == 25
    assert not mgr1.is_muted

    # Pass updated settings
    s2 = Settings(sound_enabled=False, sound_volume=85)
    mgr2 = get_sound_manager(s2)
    assert mgr2 is mgr1
    assert mgr2.get_volume() == 85
    assert mgr2.is_muted is True


def test_motion_duration_snapping_to_zero():
    """Verify duration() returns 0 ms when reduce_motion is active."""
    from ui.motion import duration, DUR_LAUNCH, DUR_SIDEBAR

    s_reduce = Settings(reduce_motion=True)
    assert duration(DUR_LAUNCH, settings=s_reduce) == 0
    assert duration(DUR_SIDEBAR, settings=s_reduce) == 0
    assert duration(150, settings=s_reduce) == 0


def test_motion_fade_and_slide_snapping(qtbot):
    """Verify fade and slide execute immediately without animation when reduce_motion is True."""
    from PySide6.QtWidgets import QWidget
    from PySide6.QtCore import QPoint
    from ui.motion import fade, slide

    widget = QWidget()
    qtbot.addWidget(widget)
    s_reduce = Settings(reduce_motion=True)

    # Fade test
    fade_finished = False
    def on_fade_done():
        nonlocal fade_finished
        fade_finished = True

    anim_fade = fade(widget, start=0.0, end=1.0, ms=200, on_finished=on_fade_done, settings=s_reduce)
    assert anim_fade is None
    assert fade_finished is True
    # Effect is removed because end is 1.0
    assert widget.graphicsEffect() is None

    # Slide test
    slide_finished = False
    def on_slide_done():
        nonlocal slide_finished
        slide_finished = True

    anim_slide = slide(widget, "pos", QPoint(0, 0), QPoint(100, 100), ms=200, on_finished=on_slide_done, settings=s_reduce)
    assert anim_slide is None
    assert slide_finished is True
    assert widget.pos() == QPoint(100, 100)


def test_motion_fade_animation_removes_effect_on_finish(qtbot):
    """Verify fade removes QGraphicsOpacityEffect after animated completion."""
    from PySide6.QtWidgets import QWidget
    from unittest.mock import patch
    from ui.motion import fade

    widget = QWidget()
    qtbot.addWidget(widget)

    done_called = False
    def on_done():
        nonlocal done_called
        done_called = True

    with patch("ui.motion.should_animate", return_value=True):
        anim = fade(widget, start=0.0, end=1.0, ms=40, on_finished=on_done)
        assert anim is not None
        assert widget.graphicsEffect() is not None
        qtbot.waitUntil(lambda: done_called, timeout=1000)
        # Effect should be cleanly removed upon completion
        assert widget.graphicsEffect() is None
